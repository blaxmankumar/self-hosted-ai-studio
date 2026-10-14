import test from 'node:test';
import assert from 'node:assert/strict';
import { isLocalOutputUrl, readLocalHistory, clearLegacyProviderCredentials } from '../src/lib/localStorage.js';

const output = '/api/local/outputs/6e9e721a-29cf-4e71-a7d3-104b44b6c8c1/frame.png';
function storage(entries = {}) {
    const map = new Map(Object.entries(entries));
    return { getItem: key => map.get(key) ?? null, removeItem: key => map.delete(key), map };
}

test('legacy cleanup removes only the old credential, preserving histories and unrelated keys', () => {
    globalThis.localStorage = storage({ muapi_key: 'obsolete', muapi_history: '[{"url":"https://old.example/image.png"}]', unrelated: 'kept' });
    globalThis.window = { location: { origin: 'http://127.0.0.1:5173' }, __MUAPI_KEY__: 'obsolete' };
    clearLegacyProviderCredentials();
    assert.equal(localStorage.getItem('muapi_key'), null);
    assert.equal(window.__MUAPI_KEY__, undefined);
    assert.equal(localStorage.getItem('unrelated'), 'kept');
    assert.equal(localStorage.getItem('muapi_history'), '[{"url":"https://old.example/image.png"}]');
});

test('legacy local history excludes remote, non-output, malformed, and cross-origin media', () => {
    globalThis.window = { location: { origin: 'http://127.0.0.1:5173' } };
    globalThis.localStorage = storage({ 'open-higgsfield.local.v1.image-history': JSON.stringify([
        { id: 'local', url: output },
        { url: 'https://example.com/image.png' },
        { url: 'http://localhost:5173' + output },
        { url: '/api/local/outputs/../../private/key' },
        { url: output + '?remote=https://example.com' },
        { url: 'data:image/png;base64,AAAA' },
        null,
    ]) });
    assert.deepEqual(readLocalHistory('open-higgsfield.local.v1.image-history'), [{ id: 'local', url: output }]);
    assert.equal(isLocalOutputUrl('http://127.0.0.1:5173' + output), true);
    assert.equal(isLocalOutputUrl('//evil.example' + output), false);
    assert.equal(isLocalOutputUrl(output.replace('frame.png', '..secret')), false);
});

test('invalid or unavailable browser storage cannot prevent startup', () => {
    globalThis.window = { location: { origin: 'http://127.0.0.1:5173' } };
    globalThis.localStorage = storage({ invalid: '{}', corrupt: 'not JSON' });
    assert.deepEqual(readLocalHistory('invalid'), []);
    assert.deepEqual(readLocalHistory('corrupt'), []);
    globalThis.localStorage = { getItem() { throw new Error('blocked'); }, removeItem() { throw new Error('blocked'); } };
    window.__MUAPI_KEY__ = 'obsolete';
    assert.doesNotThrow(clearLegacyProviderCredentials);
    assert.equal(window.__MUAPI_KEY__, undefined);
    assert.deepEqual(readLocalHistory('blocked'), []);
});
