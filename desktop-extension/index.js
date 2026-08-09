#!/usr/bin/env node
// Entry point for the cicd-runner Desktop extension.
//
// Uses @modelcontextprotocol/sdk's own transports DIRECTLY, in-process
// (rewritten 2026-08-09, replacing the subprocess-based mcp-remote
// design) rather than spawning any child process at all.
//
// History, briefly: the ORIGINAL design loaded mcp-remote in-process
// via import() -- worked, but mcp-remote's own client declares empty
// MCP capabilities and has no roots handling, and its real runtime
// entry (proxy.ts) exports no hooks, so a stale session (the
// coordinator restarting mid-session) could never be detected or
// recovered from -- confirmed real via extensive live validation, not
// assumed. A SUBPROCESS-BASED rewrite (spawning mcp-remote as a real
// child process to allow kill+respawn on staleness) was attempted
// next, and failed THREE separate, distinct ways on the real host,
// each confirmed via the real debug log:
//   1. process.execPath inside a Desktop-hosted extension is Claude.exe
//      itself, not a plain node.exe -- spawning it with a script path
//      as an argument doesn't run that script the way node.exe would.
//   2. Fixed via ELECTRON_RUN_AS_NODE, which resolved #1, but the
//      spawned child then exited cleanly (code=0) after a few seconds,
//      before ever reaching mcp-remote's own first log line.
//   3. Cross-referencing Desktop's own client-side MCP log against the
//      same timestamps confirmed the child was silently failing to
//      ever answer Desktop's initialize request, every single time --
//      a real, repeatable pattern, not a fluke -- matching Arunas's
//      own direct recollection that Claude Desktop's extension hosting
//      does not behave reliably with nested child processes spawned
//      from within an already-Electron-hosted process.
//
// This version avoids the entire subprocess problem class: there is
// exactly one long-lived process (this one), and reconnection means
// tearing down and recreating only the CLIENT-side transport object
// (talking to cicd-runner) -- the SERVER-side transport (talking to
// Desktop, via this process's own stdin/stdout) is created once and
// never touched again, confirmed correct by construction rather than
// by working around an external process's own lifecycle.
//
// mcp-remote is no longer a dependency of this extension at all --
// removed from package.json. @modelcontextprotocol/sdk (the same
// underlying package mcp-remote itself depended on, confirmed via its
// own package.json, pinned to the same major version it used) is now
// a direct dependency instead, used for its StdioServerTransport and
// StreamableHTTPClientTransport exports only -- confirmed real via
// the actual installed package's cjs build and export map, not
// assumed compatible.
const fs = require('fs');
const os = require('os');
const path = require('path');
const { StdioServerTransport } = require('@modelcontextprotocol/sdk/server/stdio.js');
const { StreamableHTTPClientTransport, StreamableHTTPError } = require('@modelcontextprotocol/sdk/client/streamableHttp.js');

// Logs to the same directory Desktop itself already uses for MCP server
// logs -- confirmed against the official MCP debugging docs
// (modelcontextprotocol.io/docs/tools/debugging): Windows is
// `%APPDATA%\Claude\logs`. Falls back to the OS temp dir when `APPDATA`
// isn't set (Linux -- manifest.json declares that as a compatible
// platform, but Claude Desktop itself only ships for macOS/Windows per
// the same docs, so `APPDATA` is never expected there).
const debugLogDir = process.env.APPDATA ? path.join(process.env.APPDATA, 'Claude', 'logs') : os.tmpdir();
const debugLogPath = path.join(debugLogDir, 'cicd-runner-debug.log');
function debugLog(line) {
  try {
    fs.appendFileSync(debugLogPath, `${new Date().toISOString()} ${line}\n`);
  } catch {
    // Debug logging must never be why the extension fails to start.
  }
}

debugLog('--- launch (sdk-direct) ---');
debugLog(`process.execPath=${process.execPath}`);
debugLog(`process.version=${process.version}`);
debugLog(`process.platform=${process.platform}`);
debugLog(`__dirname=${__dirname}`);

// X-Allowed-Directories (added 2026-08-09, carried over from the
// subprocess design unchanged in intent, changed in mechanism): MCP's
// own "roots" protocol is the spec-native way a server would normally
// learn which directories a client's user has approved, but confirmed
// real against the OLD mcp-remote-based design that a proxy sitting
// between Desktop and cicd-runner can decline to support it. THIS
// version connects Desktop directly to a real StdioServerTransport in
// this same process, with no intermediary -- but cicd-runner itself
// still only ever sees ONE MCP client identity per streamable-HTTP
// session (this extension), not Desktop's own possible roots
// declaration, so the same real substitute still applies: whatever
// directories the user selected via this extension's own user_config
// (manifest.json's "allowed_directories") arrive here as separate
// process.argv entries -- confirmed against the real MCPB spec that
// multi-select user_config values expand into separate array elements
// -- joined into one header value and passed directly to the
// StreamableHTTPClientTransport's own requestInit.headers, rather than
// a CLI --header flag (there is no CLI process to pass one to anymore).
const selectedDirectories = process.argv.slice(2);
const extraHeaders = {};
if (selectedDirectories.length > 0) {
  extraHeaders['X-Allowed-Directories'] = selectedDirectories.join(',');
}

const SERVER_URL = new URL('http://localhost:1444/mcp');

// Plugin-owned timeout for a request forwarded to cicd-runner --
// deliberately shorter than Desktop's own ~4-minute client-side
// timeout, so there's real headroom to detect and act on staleness
// before Desktop's own timeout would otherwise just present a bare,
// unexplained hang to the user. 90s is generous slack below Desktop's
// ~240s while still well above realistic run_in_directory() call
// durations for anything but the longest builds (the coordinator's own
// CICD_TIMEOUT_SECONDS defaults to 300s for the worker itself, but that
// bounds worker EXECUTION time, not a stale-session request that will
// never get a response at all -- those are distinguishable in practice
// because a stale session fails via onerror below almost immediately,
// well before this fallback would ever fire for a request that's
// actually still running normally).
const REQUEST_TIMEOUT_MS = 90_000;
const TIMEOUT_CHECK_INTERVAL_MS = 5_000;

// The real, confirmed-precise staleness signal (validated live against
// the actual coordinator during the earlier subprocess-based testing,
// still accurate here since the underlying protocol behavior hasn't
// changed): a request against a session the coordinator no longer
// recognizes (e.g. after a restart) fails with a real HTTP 404,
// surfaced by the SDK's own StreamableHTTPError with a genuine .code
// property -- confirmed directly against the installed package's real
// source, not assumed. Checking the structured .code is more precise
// than the earlier subprocess design's own stderr-text pattern match
// ever could be; the literal "Session not found" message text is kept
// as a secondary check purely as a fallback in case a differently-
// shaped error ever carries the same meaning without the same code.
function isStaleSessionError(err) {
  if (!err) return false;
  if (err instanceof StreamableHTTPError && err.code === 404) return true;
  return /Session not found/i.test(err.message || '');
}

const serverTransport = new StdioServerTransport();

let clientTransport = null;
let pending = new Map(); // id (number|string) -> { message, originalSentAt }
let reconnecting = false;
// The MCP Streamable HTTP protocol requires a fresh transport to
// complete its OWN initialize handshake before it will accept any
// other message -- confirmed real and live, not assumed: a real
// coordinator-restart test showed the retried request itself failing
// with "Session not found" and then "Bad Request: Missing session ID"
// on the fresh transport, because the retry skipped straight to
// resending the original tools/call-type request without first
// re-establishing a session on that new transport. Desktop's own
// initialize (and the notifications/initialized that follows it, per
// the standard MCP handshake sequence) are remembered here so a fresh
// transport can replay them BEFORE any other pending request is retried.
let lastInitializeMessage = null;
let lastInitializedNotification = null;

function createClientTransport() {
  return new StreamableHTTPClientTransport(SERVER_URL, {
    requestInit: { headers: extraHeaders },
  });
}

function sendErrorResponse(id, message) {
  debugLog(`sending final error response for id=${id}: ${message}`);
  serverTransport.send({
    jsonrpc: '2.0',
    id,
    error: { code: -32000, message },
  }).catch((err) => debugLog(`failed to send error response: ${err && err.stack ? err.stack : err}`));
}

function wireClientTransport(transport) {
  transport.onmessage = (message) => {
    if (message.id !== undefined && pending.has(message.id)) {
      pending.delete(message.id);
    }
    serverTransport.send(message).catch((err) => {
      debugLog(`error sending to Desktop: ${err && err.stack ? err.stack : err}`);
    });
  };

  transport.onerror = (err) => {
    debugLog(`client transport error: ${err && err.stack ? err.stack : err}`);
    if (isStaleSessionError(err)) {
      debugLog('detected stale-session signal -- reconnecting (client transport only)');
      handleStaleConnection();
    }
  };

  transport.onclose = () => {
    debugLog('client transport closed');
  };
}

// Budget-based, not attempt-count-based (confirmed correct via the
// same reasoning and tests as the earlier subprocess design): a
// request may legitimately need MORE than one retry within its own
// overall timeout window -- e.g. the coordinator restarting twice in
// quick succession. Each request's own originalSentAt (set once, at
// first send, never touched again) is what's checked against the
// budget -- only a request that has genuinely exhausted its own
// REQUEST_TIMEOUT_MS since ORIGINAL send gets failed here; anything
// still within budget is retried again, however many times that takes.
function handleStaleConnection() {
  if (reconnecting) return; // already in progress, avoid a duplicate teardown
  reconnecting = true;
  debugLog('handling stale connection');

  const old = clientTransport;
  if (old) {
    old.onmessage = undefined;
    old.onerror = undefined;
    old.onclose = undefined;
    old.close().catch(() => {});
  }

  const now = Date.now();
  const toRetry = [];
  for (const [id, info] of pending.entries()) {
    // initialize/notifications/initialized are replayed explicitly,
    // below, before anything else -- never queued into the normal
    // retry list, even in the unlikely case staleness happens during
    // the very first handshake itself.
    if (info.message.method === 'initialize' || info.message.method === 'notifications/initialized') {
      continue;
    }
    if (now - info.originalSentAt >= REQUEST_TIMEOUT_MS) {
      pending.delete(id);
      sendErrorResponse(id, 'cicd-runner connection was lost and could not be recovered in time');
    } else {
      toRetry.push([id, info.message]);
    }
  }

  clientTransport = createClientTransport();
  wireClientTransport(clientTransport);
  clientTransport.start()
    .then(async () => {
      // Re-establish the session on the fresh transport FIRST --
      // confirmed real and required, not optional: the fresh transport
      // has no session ID of its own until this completes, and any
      // other message sent before it fails with "Missing session ID".
      if (lastInitializeMessage) {
        debugLog('replaying initialize on fresh client transport');
        await clientTransport.send(lastInitializeMessage);
      }
      if (lastInitializedNotification) {
        debugLog('replaying notifications/initialized on fresh client transport');
        await clientTransport.send(lastInitializedNotification);
      }

      reconnecting = false;
      for (const [id, message] of toRetry) {
        debugLog(`retrying request id=${id} on fresh client transport`);
        clientTransport.send(message).catch((err) => {
          debugLog(`error retrying request id=${id}: ${err && err.stack ? err.stack : err}`);
        });
      }
    })
    .catch((err) => {
      reconnecting = false;
      debugLog(`failed to start/re-initialize fresh client transport: ${err && err.stack ? err.stack : err}`);
    });
}

function checkPendingTimeouts() {
  if (reconnecting) return;
  const now = Date.now();
  for (const [, info] of pending.entries()) {
    if (now - info.originalSentAt > REQUEST_TIMEOUT_MS) {
      debugLog(`request pending >${REQUEST_TIMEOUT_MS}ms since ORIGINAL send with no response -- treating as stale (timeout fallback)`);
      handleStaleConnection();
      break; // handleStaleConnection reconnects; further entries are covered next tick
    }
  }
}

serverTransport.onmessage = (message) => {
  if (message.method === 'initialize') {
    lastInitializeMessage = message;
  } else if (message.method === 'notifications/initialized') {
    lastInitializedNotification = message;
  }
  if (message.id !== undefined) {
    pending.set(message.id, { message, originalSentAt: Date.now() });
  }
  clientTransport.send(message).catch((err) => {
    debugLog(`error sending to cicd-runner: ${err && err.stack ? err.stack : err}`);
  });
};

serverTransport.onerror = (err) => {
  debugLog(`server transport (Desktop-facing) error: ${err && err.stack ? err.stack : err}`);
};

async function main() {
  clientTransport = createClientTransport();
  wireClientTransport(clientTransport);
  await clientTransport.start();
  debugLog('client transport started');

  await serverTransport.start();
  debugLog('server transport started -- relaying stdio to cicd-runner directly, no subprocess');

  setInterval(checkPendingTimeouts, TIMEOUT_CHECK_INTERVAL_MS);
}

main().catch((err) => {
  debugLog(`fatal error during startup: ${err && err.stack ? err.stack : err}`);
  console.error('Failed to start cicd-runner extension:', err);
  process.exit(1);
});

function cleanup() {
  debugLog('shutting down');
  serverTransport.close().catch(() => {});
  if (clientTransport) clientTransport.close().catch(() => {});
  process.exit(0);
}
process.on('SIGINT', cleanup);
process.on('SIGTERM', cleanup);
