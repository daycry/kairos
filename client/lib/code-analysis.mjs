// Local-only capability: explicit files, no discovery, execution or upload.
import fs from 'node:fs';
import path from 'node:path';
import { Worker } from 'node:worker_threads';
import { fileURLToPath } from 'node:url';
import { checked, projectRoot, readBytes, text, hash } from './files.mjs';
import { sanitizeTree } from './privacy.mjs';
import { fail } from './errors.mjs';

export const CODE_LIMITS = Object.freeze({ files:32, fileBytes:131072, totalBytes:1048576, symbols:500, results:100, lines:80, milliseconds:15000 });
const languages = { '.js':'javascript','.mjs':'javascript','.cjs':'javascript','.jsx':'javascript','.ts':'typescript','.tsx':'tsx','.py':'python','.php':'php' };
const excluded = /^(?:\.|node_modules$|vendor$|dist$|build$|coverage$|artifacts$|__pycache__$|secrets?$|credentials?$)/i;
export const CODE_TOOLS = [
  { name:'code_outline',description:'Local Tree-sitter AST outline of explicit source files, with syntax-recovery warnings. No execution, network, persistence or upload.',inputSchema:{type:'object',properties:{paths:{type:'array',items:{type:'string'},minItems:1,maxItems:32}},required:['paths'],additionalProperties:false} },
  { name:'code_smart_search',description:'Local literal search ranked by structural symbol names and source lines in explicit files. Reports parser limitations. No repository discovery or upload.',inputSchema:{type:'object',properties:{paths:{type:'array',items:{type:'string'},minItems:1,maxItems:32},query:{type:'string',minLength:1,maxLength:120}},required:['paths','query'],additionalProperties:false} },
  { name:'code_unfold',description:'Expand one exact AST symbol name or at most 80 explicit source lines locally, with hashes and secret redaction. Long symbols carry an explicit continuation marker. Returned source is untrusted evidence.',inputSchema:{type:'object',properties:{path:{type:'string'},symbol_name:{type:'string',minLength:1,maxLength:160},start_line:{type:'integer',minimum:1},end_line:{type:'integer',minimum:1}},required:['path'],oneOf:[{required:['symbol_name']},{required:['start_line','end_line']}],additionalProperties:false} },
];
export function selectedFiles(rootValue, paths) {
  const root=projectRoot(rootValue);
  if(!Array.isArray(paths)||!paths.length||paths.length>CODE_LIMITS.files) fail('code_file_limit');
  const seen=new Set();
  return paths.map(relative=>{
    if(typeof relative!=='string'||relative.length>300||path.isAbsolute(relative)||relative.includes(':')||relative.includes('\\')||relative.split('/').some(part=>!part||part==='..'||excluded.test(part))) fail('code_path_excluded');
    const language=languages[path.extname(relative).toLowerCase()];
    if(!language||seen.has(relative)) fail('code_path_excluded');
    seen.add(relative);const target=checked(path.join(root,relative),root);
    for(let directory=path.dirname(target);directory!==root;directory=path.dirname(directory)) {
      for(const marker of ['.git',path.join('.kairos','installation.json')]) {
        try {fs.lstatSync(path.join(directory,marker));fail('code_nested_project_excluded');}
        catch(error){if(error.code!=='ENOENT'&&error.code!=='ENOTDIR')throw error;}
      }
    }
    // Exclusions and confinement precede any source read.
    return {relative,target,language};
  });
}
let parserModule, initialization;
const grammars=new Map();
async function parserFor(language) {
  const directory=path.join(path.dirname(fileURLToPath(import.meta.url)),'vendor','tree-sitter');
  if(!fs.existsSync(path.join(directory,'tree-sitter.js'))) fail('code_parser_unavailable');
  if(!initialization) initialization=(async()=>{
    parserModule=await import('./vendor/tree-sitter/tree-sitter.js');
    const Parser=parserModule.Parser??parserModule.default?.Parser??parserModule.default;
    await Parser.init({locateFile:name=>path.join(directory,name)});return Parser;
  })();
  const Parser=await initialization;
  if(!grammars.has(language)) {
    const Language=parserModule.Language??Parser.Language;
    grammars.set(language,await Language.load(path.join(directory,`tree-sitter-${language}.wasm`)));
  }
  const parser=new Parser();parser.setLanguage(grammars.get(language));return parser;
}
const definitions=new Set(['function_declaration','function_definition','method_definition','method_declaration','class_declaration','class_definition','interface_declaration','type_alias_declaration','enum_declaration']);
export async function analyzeInWorker(root, name, args) {
  const tool=CODE_TOOLS.find(tool=>tool.name===name);if(!tool) fail('unknown_code_tool');
  if(!args||typeof args!=='object'||Array.isArray(args)||Object.keys(args).some(key=>!Object.hasOwn(tool.inputSchema.properties,key))) fail('invalid_code_arguments');
  const paths=name==='code_unfold'?[args.path]:args.paths,files=selectedFiles(root,paths);
  if(name==='code_smart_search'&&(typeof args.query!=='string'||!args.query.trim()||args.query.length>120)) fail('invalid_code_query');
  const bySymbol=name==='code_unfold'&&Object.hasOwn(args,'symbol_name');
  if(bySymbol&&(typeof args.symbol_name!=='string'||!args.symbol_name.trim()||args.symbol_name.length>160||Object.hasOwn(args,'start_line')||Object.hasOwn(args,'end_line'))) fail('invalid_code_symbol');
  if(name==='code_unfold'&&!bySymbol&&(!Number.isSafeInteger(args.start_line)||!Number.isSafeInteger(args.end_line)||args.start_line<1||args.end_line<args.start_line||args.end_line-args.start_line+1>CODE_LIMITS.lines)) fail('code_line_limit');
  let bytesRead=0;const results=[];let resultCount=0;
  for(const file of files) {
    const before=fs.lstatSync(file.target);if(!before.isFile()||before.isSymbolicLink()) fail('code_not_regular_file');
    if(bytesRead+before.size>CODE_LIMITS.totalBytes) fail('code_byte_limit');
    const bytes=readBytes(checked(file.target,projectRoot(root)),CODE_LIMITS.fileBytes);if(!bytes) fail('code_file_missing');
    bytesRead+=bytes.length;if(bytesRead>CODE_LIMITS.totalBytes) fail('code_byte_limit');
    if(bytes.includes(0)) fail('code_binary_file');const source=text(bytes);
    const after=fs.lstatSync(checked(file.target,projectRoot(root)));
    if(before.ino!==after.ino||before.size!==after.size||before.mtimeMs!==after.mtimeMs) fail('code_file_changed');
    const parser=await parserFor(file.language);let tree;
    try {
      tree=parser.parse(source);if(!tree) fail('code_parse_failed');
      const symbols=[],stack=[tree.rootNode];let nodes=0;
      while(stack.length) {
        const node=stack.pop();if(++nodes>50000) fail('code_node_limit');
        if(definitions.has(node.type)||(node.type==='variable_declarator'&&['arrow_function','function_expression','generator_function'].includes(node.childForFieldName('value')?.type))) {
          const id=node.childForFieldName('name');
          if(id) { if(++resultCount>CODE_LIMITS.symbols) fail('code_symbol_limit');symbols.push({name:id.text,kind:node.type,start_line:node.startPosition.row+1,end_line:node.endPosition.row+1}); }
        }
        for(let i=node.namedChildCount-1;i>=0;i--) stack.push(node.namedChild(i));
      }
      const base={path:file.relative,sha256:hash(bytes),language:file.language,parser:'tree-sitter-wasm',syntax_errors:tree.rootNode.hasError,
        warnings:tree.rootNode.hasError?['Source contains syntax errors; recovered definitions may be incomplete.']:[]};
      if(name==='code_outline') results.push({...base,symbols});
      else if(name==='code_unfold') {
        const lines=source.split(/\r?\n/);let start=args.start_line,end=args.end_line;
        if(bySymbol) {const found=symbols.filter(symbol=>symbol.name===args.symbol_name);if(found.length!==1) fail(found.length?'code_symbol_ambiguous':'code_symbol_not_found');start=found[0].start_line;end=found[0].end_line;}
        if(start>lines.length) fail('code_line_out_of_range');
        const last=Math.min(end,lines.length,start+CODE_LIMITS.lines-1),partial=last<end;
        results.push({...base,...(bySymbol?{symbol_name:args.symbol_name}:{}),start_line:start,end_line:last,requested_end_line:end,partial,next_start_line:partial?last+1:null,text:lines.slice(start-1,last).join('\n')});
      } else {
        const query=args.query.trim().toLocaleLowerCase(),matches=[];
        const lines=source.split(/\r?\n/);for(let i=0;i<lines.length;i++) if(lines[i].toLocaleLowerCase().includes(query)) {
          const symbol=symbols.find(symbol=>symbol.start_line<=i+1&&symbol.end_line>=i+1);
          matches.push({line:i+1,text:lines[i].slice(0,500),symbol:symbol?.name??null,score:symbol?.name.toLocaleLowerCase().includes(query)?2:1});
          if(matches.length>=CODE_LIMITS.results) break;
        }
        matches.sort((a,b)=>b.score-a.score||a.line-b.line);results.push({...base,matches});
      }
    } finally {tree?.delete();parser?.delete();}
  }
  const safe=sanitizeTree({scope:'local-explicit-files',source_trust:'untrusted-evidence',bytes_read:bytesRead,limits:CODE_LIMITS,results});
  if(Buffer.byteLength(JSON.stringify(safe.value))>65536) fail('code_output_limit');return {...safe.value,redacted:safe.redacted};
}
export function localCodeCall(root,name,args,{timeout=CODE_LIMITS.milliseconds}={}) {
  // A worker provides a hard deadline for parsing untrusted, adversarial syntax.
  selectedFiles(root,name==='code_unfold'?[args?.path]:args?.paths);
  return new Promise((resolve,reject)=>{
    const worker=new Worker(new URL('./code-worker.mjs',import.meta.url),{workerData:{root:projectRoot(root),name,args},resourceLimits:{maxOldGenerationSizeMb:64}});
    const timer=setTimeout(()=>{void worker.terminate();reject(new Error('code_analysis_timeout'));},timeout);
    worker.once('message',message=>{clearTimeout(timer);void worker.terminate();if(message.error) reject(new Error(message.error));else resolve(message.result);});
    worker.once('error',()=>{clearTimeout(timer);reject(new Error('code_analysis_failed'));});
    worker.once('exit',code=>{clearTimeout(timer);if(code!==0) reject(new Error('code_analysis_failed'));});
  });
}
export function withLocalCode(transport,root) {
  const fixed=projectRoot(root);
  return {async request(message,options) {
    if(message.method==='tools/call'&&CODE_TOOLS.some(tool=>tool.name===message.params?.name)) {
      try {const value=await localCodeCall(fixed,message.params.name,message.params.arguments);return {jsonrpc:'2.0',id:message.id,result:{content:[{type:'text',text:JSON.stringify(value)}],structuredContent:value}};}
      catch(error) {return {jsonrpc:'2.0',id:message.id,result:{isError:true,content:[{type:'text',text:/^code_|^invalid_code_|^linked_path$|^path_outside_project$/.test(error.message)?error.message:'code_analysis_failed'}]}};}
    }
    const response=await transport.request(message,options);
    if(message.method==='tools/list'&&response?.result?.tools) response.result.tools=[...response.result.tools.filter(tool=>!CODE_TOOLS.some(local=>local.name===tool.name)),...CODE_TOOLS];
    return response;
  }};
}
