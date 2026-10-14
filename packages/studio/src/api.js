// Browser transport for the self-hosted API. Requests stay on the frontend origin.
const API_PREFIX = '/api/local';
const OUTPUT_PATH = /^\/(?:api\/local\/)?outputs\/[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}\/[A-Za-z0-9][A-Za-z0-9._-]*\.(?:png|jpg|jpeg|webp|mp4)$/i;

export class LocalApiError extends Error {
    constructor(code, message, status = 0, details = null) {
        super(message);
        this.name = 'LocalApiError';
        this.code = code;
        this.status = status;
        this.details = details;
    }
}

export function localOutputUrl(value) {
    if (typeof value !== 'string' || !OUTPUT_PATH.test(value) || value.includes('..')) {
        throw new LocalApiError('UNSAFE_OUTPUT_URL', 'The backend returned an invalid local output path.');
    }
    return value.startsWith(API_PREFIX + '/') ? value : API_PREFIX + value;
}

export function isLocalOutputUrl(value) {
    return typeof value === 'string' && value.startsWith(API_PREFIX + '/outputs/') &&
        OUTPUT_PATH.test(value) && !value.includes('..');
}

function apiError(data, status) {
    const detail = data?.error || data?.detail || data;
    return new LocalApiError(
        detail?.code || 'API_ERROR',
        detail?.message || (typeof detail === 'string' ? detail : `Local API request failed (${status}).`),
        status,
        detail?.details || null,
    );
}

async function request(path, { method = 'GET', body, timeoutMs = 15000, signal } = {}) {
    const controller = new AbortController();
    const cancel = () => controller.abort();
    if (signal?.aborted) controller.abort();
    signal?.addEventListener('abort', cancel, { once: true });
    const timeout = setTimeout(cancel, timeoutMs);
    try {
        const response = await fetch(API_PREFIX + path, {
            method,
            headers: { Accept: 'application/json', ...(body ? { 'Content-Type': 'application/json' } : {}) },
            body: body ? JSON.stringify(body) : undefined,
            credentials: 'omit',
            cache: 'no-store',
            redirect: 'error',
            signal: controller.signal,
        });
        let data;
        try { data = await response.json(); }
        catch { throw new LocalApiError('INVALID_RESPONSE', 'The local API did not return JSON.', response.status); }
        if (!response.ok) throw apiError(data, response.status);
        return data;
    } catch (error) {
        if (error instanceof LocalApiError) throw error;
        if (controller.signal.aborted) {
            throw new LocalApiError(signal?.aborted ? 'CANCELLED' : 'REQUEST_TIMEOUT',
                signal?.aborted ? 'The request was cancelled.' : 'The local API request timed out.');
        }
        throw new LocalApiError('BACKEND_UNREACHABLE', 'Cannot reach the local backend. Start FastAPI and retry.');
    } finally {
        clearTimeout(timeout);
        signal?.removeEventListener('abort', cancel);
    }
}

function normalizeJob(job) {
    if (!job || typeof job.id !== 'string' || !['pending', 'running', 'completed', 'failed'].includes(job.status)) {
        throw new LocalApiError('INVALID_RESPONSE', 'The backend returned an invalid job.');
    }
    if (job.status !== 'completed') return job;
    const outputs = job.result?.outputs;
    if (!Array.isArray(outputs) || !outputs.length) {
        throw new LocalApiError('INVALID_RESULT', 'The completed job has no generated output.');
    }
    const normalized = outputs.map(output => ({
        ...(typeof output === 'object' ? output : {}),
        url: localOutputUrl(typeof output === 'string' ? output : output?.url),
    }));
    return { ...job, result: { ...job.result, outputs: normalized }, url: normalized[0].url, outputs: normalized.map(o => o.url) };
}

export const getHealth = options => request('/health', options);
export const getModels = options => request('/models', options);
export async function getOutputBlob(value, { signal, timeoutMs = 30000 } = {}) {
    const url = localOutputUrl(value);
    const controller = new AbortController();
    const cancel = () => controller.abort();
    if (signal?.aborted) controller.abort();
    signal?.addEventListener('abort', cancel, { once: true });
    const timeout = setTimeout(cancel, timeoutMs);
    try {
        const response = await fetch(url, {
            headers: { Accept: 'image/png,image/jpeg,image/webp,video/mp4' },
            credentials: 'omit', cache: 'no-store', redirect: 'error', signal: controller.signal,
        });
        if (!response.ok) {
            let data;
            try { data = await response.json(); } catch { /* A missing file may not return JSON. */ }
            throw apiError(data, response.status);
        }
        const mediaType = (response.headers.get('content-type') || '').split(';')[0].trim().toLowerCase();
        if (!['image/png', 'image/jpeg', 'image/webp', 'video/mp4'].includes(mediaType)) {
            throw new LocalApiError('INVALID_OUTPUT', 'The generated result is not supported image or video media.', response.status);
        }
        const blob = await response.blob();
        if (!blob.size) throw new LocalApiError('INVALID_OUTPUT', 'The generated result is empty.', response.status);
        return blob;
    } catch (error) {
        if (error instanceof LocalApiError) throw error;
        if (controller.signal.aborted) {
            throw new LocalApiError(signal?.aborted ? 'CANCELLED' : 'REQUEST_TIMEOUT',
                signal?.aborted ? 'The download was cancelled.' : 'The generated result download timed out.');
        }
        throw new LocalApiError('OUTPUT_UNREACHABLE', 'Cannot retrieve the generated result from the local backend.');
    } finally {
        clearTimeout(timeout);
        signal?.removeEventListener('abort', cancel);
    }
}
export async function getJobs(options) {
    const data = await request('/jobs', options);
    if (!Array.isArray(data?.jobs)) throw new LocalApiError('INVALID_RESPONSE', 'Invalid local job history.');
    return { ...data, jobs: data.jobs.map(normalizeJob) };
}
export async function getJob(id, options) {
    if (typeof id !== 'string' || !/^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$/i.test(id)) {
        throw new LocalApiError('INVALID_JOB_ID', 'Invalid job ID.');
    }
    return normalizeJob(await request('/jobs/' + id, options));
}

export async function submitGeneration(kind, params, options = {}) {
    if (!['image', 'video', 'lipsync'].includes(kind)) throw new LocalApiError('INVALID_GENERATION_TYPE', 'Unsupported generation type.');
    if (!params || typeof params !== 'object') throw new LocalApiError('INVALID_REQUEST', 'Generation parameters are required.');
    const { onRequestId, onStatus } = params;
    const payload = {};
    // The backend validates this provider-independent request schema. Old API keys,
    // callbacks and vendor-specific fields are never serialized into the request.
    for (const field of ['model', 'prompt', 'negative_prompt', 'aspect_ratio', 'resolution',
        'width', 'height', 'seed', 'duration', 'quality', 'image_url', 'video_url', 'audio_url']) {
        if (params[field] !== undefined && params[field] !== null) payload[field] = params[field];
    }
    if (!payload.image_url && Array.isArray(params.images_list) && params.images_list.length) payload.image_url = params.images_list[0];
    if (payload.seed === -1) delete payload.seed;
    for (const field of ['image_url', 'video_url', 'audio_url']) {
        if (!payload[field]) continue;
        payload[field] = localOutputUrl(payload[field]).slice(API_PREFIX.length);
    }
    const job = normalizeJob(await request('/generate/' + kind, { ...options, method: 'POST', body: payload }));
    onRequestId?.(job.id);
    onStatus?.(job);
    return job;
}

function delay(ms, signal) {
    return new Promise((resolve, reject) => {
        if (signal?.aborted) { reject(new LocalApiError('CANCELLED', 'The request was cancelled.')); return; }
        const cancel = () => {
            clearTimeout(timer);
            reject(new LocalApiError('CANCELLED', 'The request was cancelled.'));
        };
        const timer = setTimeout(() => { signal?.removeEventListener('abort', cancel); resolve(); }, ms);
        signal?.addEventListener('abort', cancel, { once: true });
    });
}

export async function pollForResult(id, { timeoutMs = 120000, intervalMs = 1000, signal, onStatus } = {}) {
    const deadline = Date.now() + timeoutMs;
    while (Date.now() < deadline) {
        const remaining = deadline - Date.now();
        const job = await getJob(id, { signal, timeoutMs: Math.max(1, Math.min(15000, remaining)) });
        onStatus?.(job);
        if (job.status === 'completed') return job;
        if (job.status === 'failed') throw apiError({ error: job.error || { code: 'GENERATION_FAILED', message: 'GPU worker inference failed.' } }, 500);
        await delay(Math.min(intervalMs, Math.max(1, deadline - Date.now())), signal);
    }
    throw new LocalApiError('JOB_TIMEOUT', 'Generation is still unfinished. The job remains saved in local history.');
}

async function generate(kind, params, { timeoutMs = 120000, intervalMs = 1000, signal, requestTimeoutMs = 15000 } = {}) {
    const job = await submitGeneration(kind, params, { signal, timeoutMs: requestTimeoutMs });
    if (job.status === 'completed') return job;
    if (job.status === 'failed') throw apiError({ error: job.error }, 500);
    return pollForResult(job.id, { timeoutMs, intervalMs, signal, onStatus: params.onStatus });
}

export const generateImage = (params, options) => generate('image', params, options);
export const generateI2I = (params, options) => generate('image', params, options);
export const generateVideo = (params, options) => generate('video', params, options);
export const generateI2V = (params, options) => generate('video', params, options);
export const processLipSync = (params, options) => generate('lipsync', params, options);

export async function uploadFile() {
    throw new LocalApiError('UPLOAD_NOT_AVAILABLE', 'Local uploads will be enabled with a validated model integration in a later phase.', 501);
}
