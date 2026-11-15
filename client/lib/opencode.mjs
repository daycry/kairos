import { randomUUID } from 'node:crypto';
import { loadInstallation } from './install.mjs';
import { ensureDispatcher, ipc } from './lifecycle.mjs';
import { checked, projectRoot, within } from './files.mjs';
import { diagnostic } from './errors.mjs';

/** Native adapters never read transcripts. Resolve the individual session's
 * directory before crossing the local IPC boundary; plugin location alone is
 * insufficient for a server that hosts several projects.
 */
function channel(root, runtime, lookup, dependencies = {}) {
  const base = projectRoot(root);
  const send = dependencies.send ?? (async (route, body) => {
    const { data } = loadInstallation(base);
    const config = await ensureDispatcher(base,data);
    return await ipc(config,route,body);
  });
  const error = dependencies.error ?? (code => process.stderr.write('kairos: '+code+'\n'));
  const scoped = async sessionID => {
    if (typeof sessionID !== 'string' || !/^[A-Za-z0-9_.:-]{1,200}$/.test(sessionID)) return null;
    const response = await lookup(sessionID);
    const info = response?.data ?? response;
    const cwd = info?.location?.directory ?? info?.directory;
    if (typeof cwd !== 'string' || !within(base,projectRoot(checked(cwd)))) return null;
    return { cwd, session_id: sessionID };
  };
  return {
    async capture(session, event, fields = {}) {
      try {
        const input = await scoped(session); if (!input) return;
        await send('/capture', { runtime, event, input: { ...fields,...input }, delivery_id: randomUUID() });
      } catch (value) { error(diagnostic(value)); }
    },
    async context(session, prompt) {
      try { const input = await scoped(session); return input ? (await send('/context',{ input: { ...(prompt ? { prompt } : {}), ...input } })).context ?? '' : ''; }
      catch (value) { error(diagnostic(value)); return ''; }
    },
  };
}

// Model-request messages are already in memory. Use only the latest user's
// bounded text as a retrieval query; never forward attachments or tool output.
function latestUserText(messages) {
  if (!Array.isArray(messages)) return '';
  for (let index=messages.length-1; index>=0; index--) {
    const message=messages[index];
    if (message?.role !== 'user') continue;
    if (typeof message.content === 'string') return message.content.slice(0,2048);
    if (!Array.isArray(message.content)) return '';
    let query='';
    for (const part of message.content) {
      if (part?.type === 'text' && typeof part.text === 'string') query+=(query ? '\n' : '')+part.text.slice(0,2048-query.length);
      if (query.length >= 2048) break;
    }
    return query;
  }
  return '';
}

export function adapterV1(root, dependencies) {
  return async ctx => {
    const memory = channel(root,'opencode-v1', async id => (await ctx.client.session.get({ path: { id }, query: { directory: ctx.directory } })).data, dependencies);
    return {
      'tool.execute.after': async (input,output) => {
        await memory.capture(input.sessionID,'PostToolUse', { tool_name: input.tool, tool_use_id: input.callID,
          tool_input: input.args, tool_response: { output: output.output, metadata: output.metadata } });
      },
      'experimental.chat.system.transform': async (input,output) => {
        const context = await memory.context(input.sessionID);
        if (context && Array.isArray(output.system)) output.system.push(context);
      },
      event: async ({ event }) => {
        if (event.type === 'session.created') await memory.capture(event.properties?.info?.id,'SessionStart');
        if (event.type === 'session.idle') await memory.capture(event.properties?.sessionID,'Stop');
      },
    };
  };
}

export function adapterV2(root, dependencies) {
  return { id: 'kairos-memory', async setup(ctx) {
    const memory = channel(root,'opencode-v2', id => ctx.session.get({ sessionID: id }), dependencies);
    const registrations = [];
    registrations.push(await ctx.tool.hook('execute.after', async event => {
      await memory.capture(event.sessionID, event.status === 'error' ? 'PostToolUseFailure' : 'PostToolUse', {
        tool_name: event.tool, tool_use_id: event.id, tool_input: event.input,
        tool_response: event.status === 'completed' ? event.result : null,
        status: event.status, error: event.status === 'error' ? String(event.error?.message ?? 'Tool execution failed') : undefined });
    }));
    registrations.push(await ctx.session.hook('context', async event => {
      // The named context hook is the primary loop. Unlike HTTP request
      // hooks its native event has no kind. Tolerate explicit primary only.
      if (event.kind !== undefined && event.kind !== 'primary') return;
      const context = await memory.context(event.sessionID,latestUserText(event.messages));
      if (context && Array.isArray(event.system)) event.system.push({ type: 'text', text: context });
    }));
    const controller = new AbortController();
    const events = (async () => {
      try {
        // Native V2 execution completion is a durable event. Legacy status
        // schemas can exist without being emitted by this client's run loop.
        for await (const event of ctx.event.subscribe({ types: ['session.created','session.execution.succeeded'], signal: controller.signal })) {
          if (event.type === 'session.created') await memory.capture(event.data?.sessionID ?? event.data?.info?.id,'SessionStart',{event_id:event.id});
          if (event.type === 'session.execution.succeeded') await memory.capture(event.data?.sessionID,'Stop',{event_id:event.id});
        }
      } catch { /* stream ends on cleanup; no fallback to another project's state */ }
    })();
    return async () => { controller.abort(); await Promise.allSettled(registrations.map(value => value.dispose())); await events; };
  } };
}
