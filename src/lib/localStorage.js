// Older hosted histories remain stored in their original keys, but are never
// replayed or rendered by the local backend frontend.
export function isLocalOutputUrl(value) {
    if (typeof value !== 'string') return false;
    try {
        const parsed = new URL(value, window.location.origin);
        return parsed.origin === window.location.origin
            && /^\/api\/local\/outputs\/[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}\/[a-zA-Z0-9][a-zA-Z0-9._-]*$/i.test(parsed.pathname)
            && !parsed.pathname.includes('..')
            && !parsed.search && !parsed.hash;
    } catch {
        return false;
    }
}

export function readLocalHistory(key) {
    try {
        const entries = JSON.parse(localStorage.getItem(key) || '[]');
        return Array.isArray(entries) ? entries.filter(entry => isLocalOutputUrl(entry?.url)) : [];
    } catch {
        return [];
    }
}

export function clearLegacyProviderCredentials() {
    try {
        // Delete only the known provider credential; preserve every history key.
        localStorage.removeItem('muapi_key');
    } catch {
        // A blocked storage implementation must not prevent opening the UI.
    }
    try { delete window.__MUAPI_KEY__; } catch { /* Ignore restricted globals. */ }
}
