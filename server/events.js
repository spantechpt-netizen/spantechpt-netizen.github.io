/**
 * Live updates over Server-Sent Events.
 *
 * Each signed-in browser holds one long-lived GET to /api/events. When
 * something happens that a person would otherwise learn of on the next
 * poll — a notification raised for them, mail arriving, a quotation changing
 * status — the server writes a small event down that stream and the page
 * refreshes the part concerned. A heartbeat every 25 seconds keeps proxies
 * from closing an idle connection, and the browser's EventSource reconnects
 * on its own if one does drop, so there is no client-side retry to write.
 *
 * Events carry only what happened and to whom, never the record itself: the
 * page fetches through the normal, permission-checked API, so a stream can
 * never hand anyone something the API would not.
 */

/** userId → Set of open responses. One person may have several tabs. */
const streams = new Map();
let nextId = 1;

export function subscribe(userId, req, res) {
  res.writeHead(200, {
    'content-type': 'text/event-stream; charset=utf-8',
    'cache-control': 'no-cache, no-transform',
    connection: 'keep-alive',
    'x-accel-buffering': 'no',   // nginx: do not buffer this response
  });
  // Tell the browser how long to wait before reconnecting, then say hello so
  // the client knows the stream is open even before anything happens.
  res.write('retry: 3000\n\n');
  write(res, 'hello', { user_id: userId, time: new Date().toISOString() });

  const key = Number(userId);
  if (!streams.has(key)) streams.set(key, new Set());
  streams.get(key).add(res);

  const cleanup = () => {
    const set = streams.get(key);
    if (set) {
      set.delete(res);
      if (!set.size) streams.delete(key);
    }
  };
  req.on('close', cleanup);
  res.on('error', cleanup);
}

function write(res, event, data) {
  try {
    res.write(`id: ${nextId += 1}\nevent: ${event}\ndata: ${JSON.stringify(data ?? {})}\n\n`);
  } catch { /* the socket is going away; cleanup follows on close */ }
}

/** Sends an event to one person, on every tab they have open. */
export function publish(userId, event, data = {}) {
  const set = streams.get(Number(userId));
  if (!set) return 0;
  for (const res of set) write(res, event, data);
  return set.size;
}

/** Sends an event to everyone connected. */
export function broadcast(event, data = {}) {
  let sent = 0;
  for (const set of streams.values()) {
    for (const res of set) { write(res, event, data); sent += 1; }
  }
  return sent;
}

/** How many streams are open, for the health endpoint and tests. */
export const connections = () => [...streams.values()].reduce((n, set) => n + set.size, 0);

// A comment line is a heartbeat the browser ignores but proxies count as traffic.
const heartbeat = setInterval(() => {
  for (const set of streams.values()) {
    for (const res of set) {
      try { res.write(': ping\n\n'); } catch { /* cleanup on close */ }
    }
  }
}, 25_000);
heartbeat.unref();
