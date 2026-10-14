// The browser never chooses an inference host. Only explicit loopback URLs are
// accepted here, so configuration mistakes cannot send media to a remote API.
const UUID = '[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}';
const JOB_PATH = new RegExp(`^jobs/${UUID}$`, 'i');
const OUTPUT_PATH = new RegExp(`^outputs/${UUID}/[a-zA-Z0-9_-]+\\.(png|jpg|jpeg|webp|mp4)$`, 'i');
const MAX_BODY_BYTES = 64 * 1024;
const LOOPBACK_HOSTS = new Set(['localhost', '127.0.0.1', '[::1]']);

export function backendConfiguration(env = process.env) {
  const url = new URL(env.LOCAL_BACKEND_URL || 'http://127.0.0.1:8000');
  if (url.protocol !== 'http:' || !LOOPBACK_HOSTS.has(url.hostname) ||
      url.username || url.password || url.pathname !== '/' || url.search || url.hash) {
    throw new Error('LOCAL_BACKEND_URL must be an HTTP loopback origin, for example http://127.0.0.1:8000.');
  }
  // Pin localhost to the IPv4 loopback used by the Windows startup scripts.
  if (url.hostname === 'localhost') url.hostname = '127.0.0.1';
  const timeout = Number(env.LOCAL_BACKEND_TIMEOUT_MS || 10000);
  if (!Number.isSafeInteger(timeout) || timeout < 100 || timeout > 120000) {
    throw new Error('LOCAL_BACKEND_TIMEOUT_MS must be an integer from 100 to 120000.');
  }
  return { origin: url.origin, timeout };
}

function jsonError(status, code, message) {
  return Response.json({ error: { code, message } }, {
    status,
    headers: { 'Cache-Control': 'no-store', 'X-Content-Type-Options': 'nosniff' },
  });
}

export function permittedPath(method, segments) {
  if (!Array.isArray(segments) || segments.some(s => typeof s !== 'string' || /[\\/]/.test(s))) return null;
  const path = segments.join('/');
  if (method === 'GET' && (['health', 'models', 'jobs'].includes(path) || JOB_PATH.test(path) || OUTPUT_PATH.test(path))) return path;
  if (method === 'POST' && (/^generate\/(image|video|lipsync)$/.test(path) || path === 'uploads')) return path;
  return null;
}

async function boundedJSON(request) {
  if (!/^application\/json(?:\s*;|$)/i.test(request.headers.get('content-type') || '')) {
    throw { status: 415, code: 'UNSUPPORTED_MEDIA_TYPE', message: 'Generation requests must contain JSON.' };
  }
  const length = request.headers.get('content-length');
  if (length && (!/^\d+$/.test(length) || Number(length) > MAX_BODY_BYTES)) {
    throw { status: 413, code: 'REQUEST_TOO_LARGE', message: 'Generation requests are limited to 64 KiB.' };
  }
  const reader = request.body?.getReader();
  const chunks = [];
  let total = 0;
  if (reader) {
    try {
      while (true) {
        const { value, done } = await reader.read();
        if (done) break;
        total += value.byteLength;
        if (total > MAX_BODY_BYTES) {
          await reader.cancel();
          throw { status: 413, code: 'REQUEST_TOO_LARGE', message: 'Generation requests are limited to 64 KiB.' };
        }
        chunks.push(value);
      }
    } finally { reader.releaseLock(); }
  }
  const bytes = new Uint8Array(total);
  let offset = 0;
  for (const chunk of chunks) { bytes.set(chunk, offset); offset += chunk.byteLength; }
  try {
    const parsed = JSON.parse(new TextDecoder('utf-8', { fatal: true }).decode(bytes));
    if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) throw new Error('Expected an object');
    return JSON.stringify(parsed);
  } catch {
    throw { status: 422, code: 'VALIDATION_ERROR', message: 'The request body must be a valid JSON object.' };
  }
}

export async function forwardToBackend(request, segments, { env = process.env, fetchImpl = fetch } = {}) {
  const path = permittedPath(request.method, segments);
  if (!path) return jsonError(404, 'LOCAL_ROUTE_NOT_FOUND', 'This local API route is not supported.');

  // CORS alone does not prevent cross-site writes. Reject browser requests from
  // another origin before reading their payload or contacting the worker.
  const incomingOrigin = request.headers.get('origin');
  if (incomingOrigin) {
    try {
      const expected = new URL(request.url);
      const supplied = new URL(incomingOrigin);
      if (!LOOPBACK_HOSTS.has(expected.hostname) || supplied.origin !== expected.origin) throw new Error('Origin mismatch');
    } catch {
      return jsonError(403, 'ORIGIN_NOT_ALLOWED', 'Use the local frontend origin to access this API.');
    }
  }
  if (path === 'uploads') return jsonError(501, 'UPLOAD_NOT_AVAILABLE', 'Local uploads will be enabled with a validated model integration.');

  let config;
  try { config = backendConfiguration(env); }
  catch (error) { return jsonError(503, 'BACKEND_CONFIGURATION_ERROR', error.message); }
  let body;
  if (request.method === 'POST') {
    try { body = await boundedJSON(request); }
    catch (error) {
      if (error.code) return jsonError(error.status, error.code, error.message);
      return jsonError(400, 'INVALID_REQUEST', 'The generation request could not be read.');
    }
  }
  try {
    const upstream = await fetchImpl(`${config.origin}/${path}`, {
      method: request.method,
      headers: { ...(body ? { 'Content-Type': 'application/json' } : {}), Accept: path.startsWith('outputs/') ? '*/*' : 'application/json' },
      body,
      cache: 'no-store',
      redirect: 'error',
      signal: AbortSignal.timeout(config.timeout),
    });
    const mediaType = (upstream.headers.get('content-type') || '').split(';')[0];
    const accepted = ['application/json', 'image/png', 'image/jpeg', 'image/webp', 'video/mp4'];
    if (!accepted.includes(mediaType)) return jsonError(502, 'INVALID_BACKEND_RESPONSE', 'The backend returned an unsupported response type.');
    return new Response(upstream.body, {
      status: upstream.status,
      headers: {
        'Content-Type': upstream.headers.get('content-type'),
        'Cache-Control': 'no-store',
        'X-Content-Type-Options': 'nosniff',
      },
    });
  } catch (error) {
    if (error.name === 'TimeoutError' || error.name === 'AbortError') {
      return jsonError(504, 'BACKEND_TIMEOUT', 'The local backend did not respond in time.');
    }
    return jsonError(503, 'BACKEND_UNAVAILABLE', 'Start the FastAPI backend on 127.0.0.1:8000, then retry the connection.');
  }
}
