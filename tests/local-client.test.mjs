import test from 'node:test';
import assert from 'node:assert/strict';
import { getHealth, getModels, getJobs, getJob, getOutputBlob, submitGeneration, pollForResult, localOutputUrl, isLocalOutputUrl, uploadFile } from '../packages/studio/src/api.js';

const ID = '12345678-1234-1234-1234-123456789abc';
const job = (status, extra = {}) => ({ id: ID, status, type: 'image', model: 'test-only', result: null, error: null, ...extra });
async function withFetch(mock, work) {
  const original = globalThis.fetch;
  globalThis.fetch = mock;
  try { await work(); } finally { globalThis.fetch = original; }
}

test('browser health/model requests use only the same-origin local API', async () => {
  const seen = [];
  await withFetch(async (url, options) => { seen.push({ url, options }); return Response.json(url.endsWith('/models') ? { models: [] } : { status: 'ok' }); }, async () => {
    assert.equal((await getHealth()).status, 'ok');
    assert.deepEqual((await getModels()).models, []);
  });
  assert.deepEqual(seen.map(s => s.url), ['/api/local/health', '/api/local/models']);
  for (const { options } of seen) {
    assert.equal(options.credentials, 'omit');
    assert.equal(options.redirect, 'error');
    assert.equal(options.headers['x-api-key'], undefined);
  }
});

test('unavailable model errors retain backend code/message instead of yielding fake output', async () => {
  await withFetch(async () => Response.json({ error: { code: 'MODEL_NOT_AVAILABLE', message: 'No worker is installed.' } }, { status: 409 }), async () => {
    await assert.rejects(submitGeneration('image', { model: 'sd15-local', prompt: 'a custom prompt' }), error => error.code === 'MODEL_NOT_AVAILABLE' && error.status === 409);
  });
});

test('submission and polling preserve job identity and normalize safe local outputs', async () => {
  let polled = 0;
  const states = [];
  await withFetch(async (url, options) => {
    if (options.method === 'POST') return Response.json(job('pending'), { status: 202 });
    polled++;
    return Response.json(polled === 1 ? job('running') : job('completed', { result: { outputs: [{ url: `/outputs/${ID}/result.png`, media_type: 'image/png' }] } }));
  }, async () => {
    let callbackID;
    const submitted = await submitGeneration('image', { model: 'test-only', prompt: 'fixture', onRequestId: id => { callbackID = id; } });
    assert.equal(callbackID, ID);
    assert.equal(submitted.status, 'pending');
    const completed = await pollForResult(ID, { intervalMs: 1, timeoutMs: 1000, onStatus: state => states.push(state.status) });
    assert.equal(completed.url, `/api/local/outputs/${ID}/result.png`);
  });
  assert.deepEqual(states, ['running', 'completed']);
});

test('GPU worker progress and result history retain the existing studio job contract', async () => {
  const states = [];
  let calls = 0;
  await withFetch(async url => {
    if (url.endsWith('/jobs')) return Response.json({ jobs: [job('completed', { result: { outputs: [{ url: `/outputs/${ID}/result.png` }] } })] });
    calls++;
    return Response.json(calls === 1 ? job('running', { progress: 42 }) : job('completed', {
      progress: 100, result: { outputs: [{ url: `/outputs/${ID}/result.png`, media_type: 'image/png' }] },
    }));
  }, async () => {
    await pollForResult(ID, { intervalMs: 1, timeoutMs: 1000, onStatus: state => states.push([state.status, state.progress]) });
    const history = await getJobs();
    assert.equal(history.jobs[0].id, ID);
    assert.equal(history.jobs[0].url, `/api/local/outputs/${ID}/result.png`);
  });
  assert.deepEqual(states, [['running', 42], ['completed', 100]]);
});

test('worker connection errors remain actionable and never return completed media', async () => {
  await withFetch(async () => Response.json({ error: { code: 'WORKER_UNAVAILABLE', message: 'GPU worker is offline. Retry after it is ready.' } }, { status: 503 }), async () => {
    await assert.rejects(submitGeneration('image', { model: 'remote-image', prompt: 'test fixture' }), error =>
      error.code === 'WORKER_UNAVAILABLE' && error.status === 503 && error.message.includes('offline'));
  });
});

test('browser generation serializes only provider-independent inputs', async () => {
  let body;
  await withFetch(async (url, options) => {
    body = JSON.parse(options.body);
    assert.equal(url, '/api/local/generate/image');
    return Response.json(job('pending'), { status: 202 });
  }, async () => {
    await submitGeneration('image', {
      model: 'remote-image', prompt: 'test fixture', aspect_ratio: '1:1',
      worker_url: 'https://worker.example', worker_token: 'test-secret', api_key: 'legacy-secret', seed: -1,
    });
  });
  assert.deepEqual(body, { model: 'remote-image', prompt: 'test fixture', aspect_ratio: '1:1' });
});

test('result downloads fetch same-origin bytes and preserve image media type', async () => {
  const bytes = new Uint8Array([137, 80, 78, 71]); // Transport fixture only, never a generated result.
  await withFetch(async (url, options) => {
    assert.equal(url, `/api/local/outputs/${ID}/result.png`);
    assert.equal(options.credentials, 'omit');
    assert.equal(options.redirect, 'error');
    return new Response(bytes, { headers: { 'content-type': 'image/png' } });
  }, async () => {
    const blob = await getOutputBlob(`/outputs/${ID}/result.png`);
    assert.equal(blob.type, 'image/png');
    assert.deepEqual(new Uint8Array(await blob.arrayBuffer()), bytes);
  });
});

test('missing, empty and invalid results cannot be downloaded as generated images', async () => {
  await withFetch(async () => Response.json({ error: { code: 'OUTPUT_NOT_FOUND', message: 'Generated file is missing.' } }, { status: 404 }), async () => {
    await assert.rejects(getOutputBlob(`/outputs/${ID}/result.png`), error => error.code === 'OUTPUT_NOT_FOUND' && error.status === 404);
  });
  for (const response of [Response.json({ status: 'not an image' }), new Response(null, { headers: { 'content-type': 'image/png' } })]) {
    await withFetch(async () => response, async () => {
      await assert.rejects(getOutputBlob(`/outputs/${ID}/result.png`), error => error.code === 'INVALID_OUTPUT');
    });
  }
  let calls = 0;
  await withFetch(async () => { calls++; }, async () => {
    await assert.rejects(getOutputBlob('https://example.com/image.png'), error => error.code === 'UNSAFE_OUTPUT_URL');
  });
  assert.equal(calls, 0);
});

test('failed jobs stop polling and timeouts remain explicit', async () => {
  let calls = 0;
  await withFetch(async () => { calls++; return Response.json(job('failed', { error: { code: 'INFERENCE_FAILED', message: 'worker failed' } })); }, async () => {
    await assert.rejects(pollForResult(ID, { timeoutMs: 1000, intervalMs: 1 }), error => error.code === 'INFERENCE_FAILED');
  });
  assert.equal(calls, 1);
  await withFetch(async () => Response.json(job('pending')), async () => {
    await assert.rejects(pollForResult(ID, { timeoutMs: 5, intervalMs: 1 }), error => error.code === 'JOB_TIMEOUT');
  });
});

test('remote media, traversal, incomplete results and invalid job identifiers are rejected', async () => {
  assert.equal(localOutputUrl(`/outputs/${ID}/result.png`), `/api/local/outputs/${ID}/result.png`);
  assert.equal(isLocalOutputUrl('https://api.muapi.ai/old.png'), false);
  for (const url of ['https://example.com/image.png', `//outputs/${ID}/image.png`, `/outputs/${ID}/../image.png`]) {
    assert.throws(() => localOutputUrl(url), error => error.code === 'UNSAFE_OUTPUT_URL');
  }
  await assert.rejects(getJob('../old'), error => error.code === 'INVALID_JOB_ID');
  await withFetch(async () => Response.json(job('completed')), async () => {
    await assert.rejects(getJob(ID), error => error.code === 'INVALID_RESULT');
  });
});

test('uploads cannot silently fall back to a remote provider', async () => {
  let calls = 0;
  await withFetch(async () => { calls++; }, async () => {
    await assert.rejects(uploadFile(), error => error.code === 'UPLOAD_NOT_AVAILABLE');
  });
  assert.equal(calls, 0);
});
