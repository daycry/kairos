import { createInterface } from 'node:readline/promises';
import { VERSION, CLIENT_PATHS } from './config.mjs';
import { planInstall, preview, applyInstall, recover } from './install.mjs';
import { MCPTransport, doctor, bridge } from './mcp.mjs';
import { fail, diagnostic } from './errors.mjs';
import { loadInstallation } from './install.mjs';
import { lifecycleConfig } from './lifecycle-config.mjs';
import { runHook, startDispatcher, ensureDispatcher, ipc } from './lifecycle.mjs';
import { Outbox } from './outbox.mjs';
import { withLocalCode } from './code-analysis.mjs';

const HELP = `Kairos ${VERSION} — one MCP connection for agent memory

Usage:
  kairos install --client claude|codex|opencode|all --url BASE_URL
    --project PROJECT_ID --key-file PRIVATE_FILE [--root DIRECTORY]
    [--opencode-version 1|2] [--capture off|summary|full] [--context off|auto]
    [--state-dir PRIVATE_DIRECTORY] [--code-analysis off|on] [--dry-run | --yes] [--replace]
  kairos doctor [--root DIRECTORY] [--online]
  kairos recover [--root DIRECTORY] [--dry-run | --yes] [--unlock]
  kairos mcp --url BASE_URL --key-file PRIVATE_FILE [--code-analysis on --root DIRECTORY]
  kairos sync [--root DIRECTORY]
  kairos status [--root DIRECTORY]
  kairos queue-retry --event-id UUID [--root DIRECTORY] --yes
  kairos queue-retire --event-id UUID [--root DIRECTORY] --yes

Install uses a stable project-local copy of this Node package. Secrets remain in
the selected private file outside the project. No Python or manual env export.
Non-interactive install previews changes unless --yes is supplied. It does not
enable capture unless explicitly selected; hooks require the client's own trust
review. The project policy must independently allow capture. No models change.
--unlock is only for explicit recovery of a dead installer's stale lock.
`;

function parse(argv) {
  if (!argv.length || argv.includes('--help') || argv.includes('-h')) return { command: 'help' };
  if (argv.length === 1 && ['--version', '-v'].includes(argv[0])) return { command: 'version' };
  const [command, ...rest] = argv;
  const commands = {
    install: { values: ['root','client','url','project','key-file','opencode-version','capture','context','state-dir','code-analysis'], flags: ['yes','dry-run','replace'] },
    doctor: { values: ['root'], flags: ['online'] },
    recover: { values: ['root'], flags: ['yes','dry-run','unlock'] },
    mcp: { values: ['url','key-file','root','code-analysis'], flags: [] },
    hook: { values: ['root','runtime','event'], flags: [] },
    daemon: { values: ['root'], flags: [] },
    sync: { values: ['root'], flags: [] },
    status: { values: ['root'], flags: [] },
    'queue-retry': { values:['root','event-id'],flags:['yes'] },
    'queue-retire': { values:['root','event-id'],flags:['yes'] },
  };
  if (!Object.hasOwn(commands, command)) fail('unknown_command');
  const schema = commands[command], result = { command, root: '.' }, seen = new Set();
  for (let index = 0; index < rest.length; index++) {
    const match = /^--([a-z-]+)(?:=(.*))?$/.exec(rest[index]);
    if (!match || seen.has(match[1])) fail('invalid_argument');
    const [,name, inline] = match; seen.add(name);
    if (schema.flags.includes(name)) {
      if (inline !== undefined) fail('invalid_argument');
      result[name] = true;
    } else if (schema.values.includes(name)) {
      const value = inline ?? rest[++index];
      if (!value || value.startsWith('--')) fail('missing_argument_value');
      result[name] = value;
    } else fail('unknown_option');
  }
  return result;
}

export async function main(argv = process.argv.slice(2), { input = process.stdin, output = process.stdout, errors = process.stderr } = {}) {
  const options = parse(argv);
  if (options.command === 'help') { output.write(HELP); return 0; }
  if (options.command === 'version') { output.write(VERSION + '\n'); return 0; }
  if (options.command === 'hook') return await runHook({ root: options.root, runtime: options.runtime, event: options.event, input, output, errors });
  if (['daemon','sync','status','queue-retry','queue-retire'].includes(options.command)) {
    const { root, data } = loadInstallation(options.root);
    if (options.command === 'daemon') {
      const handle = await startDispatcher(lifecycleConfig(root,data), { errors });
      const stop = () => { void handle.close(); };
      process.once('SIGINT', stop); process.once('SIGTERM', stop);
    } else {
      const operator=options.command.startsWith('queue-');
      if(operator&&(!options.yes||!options['event-id'])) fail('explicit_queue_action_required');
      if(options.command==='queue-retire') {
        if(!/^[a-f0-9-]{36}$/i.test(options['event-id'])) fail('invalid_capture_identity');
        const config=lifecycleConfig(root,data);
        let result;
        try { result=await ipc(config,'/retire',{event_id:options['event-id']},{timeout:600}); }
        catch(error) {
          if(!['dispatcher_not_running','dispatcher_unavailable'].includes(error.message)) throw error;
          const queue=new Outbox(config.directory,config.binding);
          try { const row=queue.retire(options['event-id']); result={event_id:row.event_id,status:row.phase}; }
          finally { queue.close(); }
        }
        output.write(JSON.stringify(result,null,2)+'\n'); return 0;
      }
      const config = options.command === 'sync'||operator ? await ensureDispatcher(root,data) : lifecycleConfig(root,data);
      const route=operator?(options.command==='queue-retry'?'/retry':'/retire'):options.command==='sync'?'/sync':'/status';
      output.write(JSON.stringify(await ipc(config,route,operator?{event_id:options['event-id']}:{}),null,2)+'\n');
    }
    return 0;
  }
  if (options.command === 'mcp') {
    if (!options.url || !options['key-file']) fail('missing_connection_arguments');
    const mode=options['code-analysis']??'off';if(!['on','off'].includes(mode)) fail('invalid_code_analysis_option');
    if(mode==='on'&&!argv.some(arg=>arg==='--root'||arg.startsWith('--root='))) fail('explicit_code_root_required');
    const transport=new MCPTransport(options.url, options['key-file']);
    await bridge({ input, output, errors, transport:mode==='on'?withLocalCode(transport,options.root):transport });
    return 0;
  }
  let prompt;
  const interactive = options.command === 'install' && !!input.isTTY && !!output.isTTY && !options['dry-run'];
  try {
    if (interactive) {
      prompt = createInterface({ input, output });
      if (!options.client) options.client = (await prompt.question('Client [claude/codex/opencode/all] (all): ')).trim() || 'all';
      if (!options.url) options.url = (await prompt.question('Kairos base URL (http://127.0.0.1:5173): ')).trim() || 'http://127.0.0.1:5173';
      if (!options.project) options.project = (await prompt.question('Authorized project ID: ')).trim();
      if (!options['key-file']) options['key-file'] = (await prompt.question('Private key file outside the project: ')).trim();
      if (['all','opencode'].includes(options.client) && !options['opencode-version']) {
        options['opencode-version'] = (await prompt.question('OpenCode config generation [1/2]: ')).trim();
      }
    }
    let result;
    if (options.command === 'install') {
      if (!options.client || !options.url || !options.project || !options['key-file']) fail('missing_installation_arguments');
      const clients = options.client === 'all' ? Object.keys(CLIENT_PATHS) : [options.client];
      const version = options['opencode-version'] === undefined ? undefined : Number(options['opencode-version']);
      if (version !== undefined && ![1, 2].includes(version)) fail('invalid_opencode_version');
      const automation = {};
      for (const name of ['capture','context']) if (options[name] !== undefined) automation[name] = options[name];
      if (options['state-dir'] !== undefined) automation.state_directory = options['state-dir'];
      const plan = planInstall({ root: options.root, clients, url: options.url, project: options.project,
        keyFile: options['key-file'], openCodeVersion: version, replace: !!options.replace, automation,codeAnalysis:options['code-analysis'] });
      let apply = !!options.yes && !options['dry-run'];
      if (interactive && !options.yes) {
        output.write(JSON.stringify(preview(plan), null, 2) + '\n');
        apply = /^(?:y|yes|s|si|sí)$/i.test((await prompt.question('Apply these reviewed changes? [y/N]: ')).trim());
      }
      result = apply ? applyInstall(plan) : preview(plan);
    } else if (options.command === 'doctor') result = await doctor(options.root, { online: !!options.online });
    else result = recover(options.root, { apply: !!options.yes && !options['dry-run'], unlock: !!options.unlock });
    output.write(JSON.stringify(result, null, 2) + '\n');
    return result.status === 'degraded' ? 1 : 0;
  } finally { prompt?.close(); }
}

export async function run(argv) {
  try { return await main(argv); }
  catch (error) { process.stderr.write('kairos: ' + diagnostic(error) + '\n'); return 1; }
}
