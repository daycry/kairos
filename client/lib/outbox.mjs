import fs from 'node:fs';
import path from 'node:path';
import { randomUUID } from 'node:crypto';
import { atomicWrite, checked, jsonBytes, readBytes, sameBytes, text } from './files.mjs';
import { canonical, digest } from './capture.mjs';
import { fail } from './errors.mjs';

const PHASES=new Set(['pending','unknown','accepted','complete','failed','retired']);
const TERMINAL=new Set(['complete','retired']);
const copy=value=>JSON.parse(JSON.stringify(value));
const alive=pid=>{ try { process.kill(pid,0); return true; } catch(error) { return error.code!=='ESRCH'; } };
const size=row=>Buffer.byteLength(canonical(row));

const WAITING=new Set(['pending','unknown','accepted']);
/** What `kairos doctor` reads of the queue on this disk: a READ-ONLY replay of the snapshot and the journal. It takes no lock (the dispatcher holds it), creates and rewrites nothing,
 * reads no source file and sends nothing anywhere. Returns null when there is no queue; otherwise `{pending, oldest_seconds}` (captures that still wait for the server: pending,
 * unknown or accepted, by `admitted_at`); a queue that cannot be replayed throws, and the caller reports it as unreadable. */
export function queueAge(directory,binding,now=Date.now()) {
  const root=checked(directory),rows=new Map(); let seq=0;
  const snapshot=readBytes(path.join(root,'queue.json'),16*1024*1024);
  if(snapshot) {
    let record; try { record=JSON.parse(text(snapshot)); } catch { fail('capture_state_corrupt'); }
    const {sha256,...body}=record;
    if(![1,2].includes(body.schema)||body.binding!==binding||!Number.isSafeInteger(body.seq)||!Array.isArray(body.rows)||digest(body)!==sha256) fail('capture_state_corrupt');
    seq=body.seq; for(const row of body.rows) rows.set(row.key,row);
  }
  const journal=readBytes(path.join(root,'queue.jsonl'),32*1024*1024);
  if(journal) {
    const source=text(journal),end=source.lastIndexOf('\n')+1;  // a line still being written (no newline yet) is not read
    for(const line of source.slice(0,end).split('\n').filter(Boolean)) {
      let record; try { record=JSON.parse(line); } catch { fail('capture_journal_corrupt'); }
      const {sha256,...body}=record;
      if(body.binding!==binding||digest(body)!==sha256||!Number.isSafeInteger(body.seq)) fail('capture_journal_corrupt');
      if(body.seq<=seq) continue;
      if(body.seq!==seq+1) fail('capture_journal_gap');
      if(body.op==='remove') rows.delete(body.key); else rows.set(body.row.key,body.row);
      seq=body.seq;
    }
  }
  if(!snapshot&&!journal) return null;
  const waiting=[...rows.values()].filter(row=>WAITING.has(row.phase));
  const times=waiting.map(row=>Date.parse(row.admitted_at)).filter(Number.isFinite);
  return {pending:waiting.length,oldest_seconds:times.length?Math.max(0,Math.round((now-Math.min(...times))/1000)):0};
}

/** Source files are separate from the receipt journal. Terminal cache eviction
 * requires Dispatcher to reconcile every cache miss before a new admission. */
export class Outbox {
  constructor(directory,binding,{maxRecords=10000,maxPending=200,maxBytes=8*1024*1024,isAlive=alive,now=()=>new Date().toISOString()}={}) {
    if(!/^[a-f0-9]{64}$/.test(binding)) fail('invalid_capture_binding');
    this.root=checked(directory); fs.mkdirSync(this.root,{recursive:true,mode:0o700}); checked(this.root);
    this.binding=binding; this.limits={maxRecords,maxPending,maxBytes}; this.now=now;
    this.rows=new Map(); this.seq=0; this.writes=0; this.bytes=0; this.sources=0; this.sourceBytes=0;
    this.lock=checked(path.join(this.root,'queue.lock'),this.root);
    const guard=checked(path.join(this.root,'queue.recovery.lock'),this.root),owner=jsonBytes({pid:process.pid,nonce:randomUUID()}); let guardFD;
    // All acquisitions take this guard. A crash during recovery fails closed;
    // a dead guard requires quiescent operator recovery, never auto-unlink.
    try { guardFD=fs.openSync(guard,'wx',0o600); } catch(error) { if(error.code==='EEXIST') fail('capture_state_busy'); throw error; }
    try {
      fs.writeFileSync(guardFD,owner); fs.fsyncSync(guardFD);
      const previous=readBytes(this.lock,8192);
      if(previous) {
        let parsed; try { parsed=JSON.parse(text(previous)); } catch { fail('invalid_capture_lock'); }
        if(!Number.isSafeInteger(parsed.pid)||parsed.pid<1||typeof parsed.nonce!=='string') fail('invalid_capture_lock');
        if(isAlive(parsed.pid)) fail('capture_state_busy');
        if(!sameBytes(previous,readBytes(this.lock,8192))) fail('capture_lock_changed');
        fs.unlinkSync(this.lock);
      }
      const fd=fs.openSync(this.lock,'wx',0o600);
      try { fs.writeFileSync(fd,owner); fs.fsyncSync(fd); this.owner=owner; } finally { fs.closeSync(fd); }
    } finally { fs.closeSync(guardFD); if(sameBytes(readBytes(guard,8192),owner)) fs.unlinkSync(guard); }
    this.snapshot=checked(path.join(this.root,'queue.json'),this.root);
    this.journal=checked(path.join(this.root,'queue.jsonl'),this.root);
    this.sourceRoot=checked(path.join(this.root,'sources'),this.root); fs.mkdirSync(this.sourceRoot,{recursive:true,mode:0o700});
    try { this.restore(); } catch(error) { this.close(); throw error; }
  }
  close() { if(this.owner) { if(sameBytes(readBytes(this.lock,8192),this.owner)) fs.unlinkSync(this.lock); this.owner=null; } }
  sourcePath(key) { if(!/^[a-f0-9]{64}$/.test(key)) fail('invalid_capture_record'); return checked(path.join(this.sourceRoot,key+'.json'),this.sourceRoot); }
  discardSource(key) {
    const file=this.sourcePath(key);let info;
    try { info=fs.lstatSync(file); } catch(error) { if(error.code==='ENOENT') return;throw error; }
    if(!info.isFile()||info.isSymbolicLink()) fail('invalid_regular_file');
    fs.unlinkSync(file);
  }
  remove(key) {
    const old=this.rows.get(key); if(!old) return;
    this.bytes-=size(old); if(old.source_bytes) { this.sources--; this.sourceBytes-=old.source_bytes; } this.rows.delete(key);
  }
  put(row) {
    if(!row||!/^[a-f0-9]{64}$/.test(row.key)||!/^[a-f0-9]{64}$/.test(row.semantic_hash)||!PHASES.has(row.phase)||typeof row.event_id!=='string'||!Number.isSafeInteger(row.attempts)||row.source_bytes&&(!Number.isSafeInteger(row.source_bytes)||row.source_bytes<0)) fail('invalid_capture_record');
    this.remove(row.key); this.rows.set(row.key,copy(row)); this.bytes+=size(row);
    if(row.source_bytes) { this.sources++; this.sourceBytes+=row.source_bytes; }
  }
  restore() {
    let migrate=false; const snapshot=readBytes(this.snapshot,16*1024*1024);
    if(snapshot) {
      let record; try { record=JSON.parse(text(snapshot)); } catch { fail('capture_state_corrupt'); }
      const {sha256,...body}=record;
      if(![1,2].includes(body.schema)||body.binding!==this.binding||!Number.isSafeInteger(body.seq)||body.seq<0||!Array.isArray(body.rows)||digest(body)!==sha256) fail('capture_state_corrupt');
      this.seq=body.seq; migrate=body.schema===1; for(const row of body.rows) this.put(row);
    }
    const journal=readBytes(this.journal,32*1024*1024);
    if(journal) {
      const source=text(journal),end=source.lastIndexOf('\n')+1;
      for(const line of source.slice(0,end).split('\n').filter(Boolean)) {
        let record; try { record=JSON.parse(line); } catch { fail('capture_journal_corrupt'); }
        const {sha256,...body}=record;
        if(body.binding!==this.binding||digest(body)!==sha256||!Number.isSafeInteger(body.seq)) fail('capture_journal_corrupt');
        migrate ||= !!body.row?.event;
        if(body.seq<=this.seq) continue;
        if(body.seq!==this.seq+1) fail('capture_journal_gap');
        if(body.op==='remove'&&/^[a-f0-9]{64}$/.test(body.key)) this.remove(body.key); else this.put(body.row);
        this.seq=body.seq;
      }
      if(end!==source.length) atomicWrite(this.journal,Buffer.from(source.slice(0,end)));
    }
    for(const old of [...this.rows.values()]) if(old.event) {
      const row={...old},event=row.event; delete row.event;
      if(!['accepted','complete','retired'].includes(row.phase)) {
        const bytes=jsonBytes(event); atomicWrite(this.sourcePath(row.key),bytes); row.source_bytes=bytes.length; row.source_hash=digest(event);
      }
      this.put(row); migrate=true;
    }
    if(migrate||!snapshot) this.checkpoint();
    for(const row of [...this.rows.values()]) {
      if(row.source_bytes) {
        try { this.event(row); } catch(error) {
          if(error.message!=='capture_source_corrupt') throw error;
          if(row.phase==='failed'&&row.error_code==='capture_source_corrupt') continue;
          this.update(row.key,{phase:'failed',error_code:'capture_source_corrupt'},{hydrate:false});
        }
      }
      else this.discardSource(row.key);
    }
    this.compact(); this.budget();
  }
  event(row) {
    if(!row.source_bytes) return undefined;
    let bytes,value;
    try { bytes=readBytes(this.sourcePath(row.key),262144); } catch(error) {
      if(['invalid_regular_file','file_too_large'].includes(error.code)&&fs.lstatSync(this.sourcePath(row.key)).isFile()) fail('capture_source_corrupt');
      throw error;
    }
    try { value=JSON.parse(text(bytes)); } catch { fail('capture_source_corrupt'); }
    if(bytes.length!==row.source_bytes||digest(value)!==row.source_hash||value.event_id!==row.event_id||value.item_id!==row.item_id) fail('capture_source_corrupt');
    return value;
  }
  budget(extra) {
    const bytes=this.bytes+this.sourceBytes+(extra?size(extra)+(extra.source_bytes??0):0);
    if(this.rows.size+(extra?1:0)>this.limits.maxRecords||this.sources+(extra?.source_bytes?1:0)>this.limits.maxPending||bytes>this.limits.maxBytes) fail('capture_queue_full');
  }
  commit(change) {
    if(this.uncertain) fail('capture_state_uncertain');
    if(!this.owner||!sameBytes(readBytes(this.lock,8192),this.owner)) fail('capture_owner_lost');
    const body={seq:this.seq+1,binding:this.binding,...change},bytes=Buffer.from(canonical({...body,sha256:digest(body)})+'\n');
    const fd=fs.openSync(checked(this.journal,this.root),fs.constants.O_WRONLY|fs.constants.O_CREAT|fs.constants.O_APPEND|(fs.constants.O_NOFOLLOW||0),0o600);
    try { let offset=0; while(offset<bytes.length) { const count=fs.writeSync(fd,bytes,offset,bytes.length-offset); if(!count) fail('capture_write_failed'); offset+=count; } fs.fsyncSync(fd); }
    catch { this.uncertain=true; fail('capture_state_uncertain'); } finally { fs.closeSync(fd); }
    if(change.op==='remove') this.remove(change.key); else this.put(change.row);
    this.seq++; this.writes++; if(this.writes>=128||fs.statSync(this.journal).size>1024*1024) this.checkpoint();
  }
  checkpoint() {
    const body={schema:2,binding:this.binding,seq:this.seq,rows:[...this.rows.values()]};
    atomicWrite(this.snapshot,jsonBytes({...body,sha256:digest(body)})); atomicWrite(this.journal,Buffer.alloc(0)); this.writes=0;
  }
  compact(reserve=0) {
    for(const row of this.rows.values()) {
      if(this.rows.size+reserve<=this.limits.maxRecords&&this.bytes+this.sourceBytes<this.limits.maxBytes*0.9) break;
      if(TERMINAL.has(row.phase)&&!row.source_bytes&&!(row.error_code==='operator_retired'&&!row.receipt)) this.commit({op:'remove',key:row.key});
    }
  }
  has(key) { return this.rows.has(key); }
  admit(spec,confirmed=null) {
    if(spec.ignored) return {status:'ignored',reason:spec.ignored};
    const previous=this.rows.get(spec.key);
    if(previous) { if(previous.semantic_hash!==spec.semantic_hash) fail('capture_identity_conflict'); return {status:previous.phase,event_id:previous.event_id,duplicate:true}; }
    this.compact(1); const now=this.now();
    const row={key:spec.key,semantic_hash:spec.semantic_hash,phase:confirmed?.phase??'pending',attempts:0,admitted_at:now,updated_at:now,event_id:spec.event.event_id,item_id:spec.event.item_id,redacted:!!spec.redacted};
    if(confirmed) { row.receipt=copy(confirmed.receipt); if(confirmed.phase==='failed') row.error_code='capture_processing_failed'; }
    else {
      let event={...copy(spec.event),occurred_at:now}; const draft=readBytes(this.sourcePath(row.key),262144);
      if(draft) { let parsed; try { parsed=JSON.parse(text(draft)); } catch { fail('capture_source_corrupt'); }
        const {occurred_at,...old}=parsed; if(canonical(old)!==canonical(spec.event)) fail('capture_identity_conflict'); event=parsed; }
      const bytes=jsonBytes(event); row.source_bytes=bytes.length; row.source_hash=digest(event); this.budget(row); atomicWrite(this.sourcePath(row.key),bytes);
    }
    this.budget(row); this.commit({row}); return {status:row.phase,event_id:row.event_id,duplicate:!!confirmed};
  }
  update(key,change,{hydrate=true}={}) {
    const old=this.rows.get(key); if(!old) fail('capture_record_missing');
    if(Object.keys(change).some(name=>!['phase','receipt','attempts','failures','error_code','next_attempt_at'].includes(name))||change.phase&&!PHASES.has(change.phase)) fail('invalid_capture_update');
    const row={...old,...copy(change),updated_at:this.now()};
    if(['accepted','complete','retired'].includes(row.phase)) { delete row.source_bytes; delete row.source_hash; }
    this.remove(key); try { this.budget(row); } finally { this.put(old); }
    this.commit({row});
    if(old.source_bytes&&!row.source_bytes) this.discardSource(key);
    return {...copy(row),...(hydrate&&row.source_bytes?{event:this.event(row)}:{})};
  }
  retry(eventID) {
    const row=[...this.rows.values()].find(row=>row.event_id===eventID);
    if(!row||row.phase!=='failed') fail('capture_retry_not_available');
    if(row.error_code==='capture_source_corrupt') fail('capture_source_repair_required');
    return this.update(row.key,{phase:row.source_bytes?'unknown':'accepted',attempts:0,error_code:null,next_attempt_at:0});
  }
  retire(eventID) {
    const row=[...this.rows.values()].find(row=>row.event_id===eventID);
    if(!row||!['pending','unknown','failed'].includes(row.phase)) fail('capture_retire_not_available');
    return this.update(row.key,{phase:'retired',error_code:'operator_retired'});
  }
  pending(limit=5,now=Infinity,hydrate=true) {
    return [...this.rows.values()].filter(row=>['pending','unknown','accepted'].includes(row.phase)&&(row.next_attempt_at??0)<=now).slice(0,limit)
      .map(row=>({...copy(row),...(hydrate&&row.source_bytes?{event:this.event(row)}:{})}));
  }
  status() {
    const phases=Object.fromEntries([...PHASES].map(phase=>[phase,0])); for(const row of this.rows.values()) phases[row.phase]++;
    return {phases,records:this.rows.size,sequence:this.seq,bytes:this.bytes+this.sourceBytes,processing_failed:[...this.rows.values()].filter(row=>row.error_code==='capture_processing_failed').length,
      recent:[...this.rows.values()].slice(-20).map(row=>({event_id:row.event_id,item_id:row.item_id,phase:row.phase,attempts:row.attempts,error_code:row.error_code??null}))};
  }
}
