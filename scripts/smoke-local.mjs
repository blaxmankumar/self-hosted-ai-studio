import assert from 'node:assert/strict';

// Integration check against the user's own running loopback servers. This never
// submits a job to a configured model or contacts a remote inference service.
const frontend = 'http://127.0.0.1:3000';
const backend = 'http://127.0.0.1:8000';
let checks = 0;
async function json(url, init = {}) {
  const response = await fetch(url, { ...init, redirect: 'error', signal: AbortSignal.timeout(30000) });
  return { response, data: await response.json() };
}
for (const origin of [backend, frontend + '/api/local']) {
  const { response, data } = await json(origin + '/health');
  assert.equal(response.status, 200);
  assert.equal(data.status, 'ok');
  assert.equal(data.inference_ready, false, 'This foundation smoke test expects no model adapter.');
  assert.equal(data.available_models, 0);
  checks++;
  const catalog = await json(origin + '/models');
  assert.equal(catalog.response.status, 200);
  assert.ok(catalog.data.models.every(model => !model.available && !model.configured));
  checks++;
  assert.equal((await json(origin + '/jobs')).response.status, 200);
  checks++;
  for (const kind of ['image', 'video', 'lipsync']) {
    const unavailable = await json(origin + '/generate/' + kind, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ model: 'unregistered-smoke-check', prompt: 'A custom lighthouse scene at dawn' }),
    });
    assert.equal(unavailable.response.status, 409);
    assert.equal(unavailable.data.error.code, 'MODEL_NOT_AVAILABLE');
    checks++;
  }
}
const foreign = await json(frontend + '/api/local/generate/image', {
  method: 'POST', headers: { 'Content-Type': 'application/json', Origin: 'https://foreign.example' },
  body: JSON.stringify({ model: 'unregistered-smoke-check', prompt: 'test' }),
});
assert.equal(foreign.response.status, 403);
assert.equal(foreign.data.error.code, 'ORIGIN_NOT_ALLOWED');
checks++;
const missing = await json(frontend + '/api/local/jobs/00000000-0000-4000-8000-000000000000');
assert.equal(missing.response.status, 404);
assert.equal(missing.data.error.code, 'JOB_NOT_FOUND');
checks++;
const upload = await json(frontend + '/api/local/uploads', { method: 'POST' });
assert.equal(upload.response.status, 501);
assert.equal(upload.data.error.code, 'UPLOAD_NOT_AVAILABLE');
checks++;
const page = await fetch(frontend + '/studio', { signal: AbortSignal.timeout(30000) });
assert.equal(page.status, 200);
assert.ok(page.headers.get('content-security-policy')?.includes("connect-src 'self'"));
assert.ok(!(await page.text()).includes('Enter your Muapi'));
checks++;
console.log(`PASS: ${checks} live local integration checks (no inference executed).`);
