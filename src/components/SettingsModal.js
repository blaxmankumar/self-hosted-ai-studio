export function SettingsModal(onClose) {
    const overlay = document.createElement('div');
    overlay.className = 'fixed inset-0 bg-black/80 flex items-center justify-center z-[100] px-6';
    const modal = document.createElement('div');
    modal.className = 'w-full max-w-md bg-panel-bg p-6 rounded-3xl border border-white/10 text-white';
    modal.setAttribute('role', 'dialog');
    modal.setAttribute('aria-modal', 'true');
    modal.setAttribute('aria-labelledby', 'local-settings-title');
    modal.innerHTML = `
        <h2 id="local-settings-title" class="text-xl font-bold mb-4">Local backend settings</h2>
        <p class="text-secondary text-sm mb-4">The studio connects to the backend running on this computer. No API key is required.</p>
        <p class="text-secondary text-sm mb-4">Model choices appear when a local adapter is implemented, configured with model paths in <code>backend/.env</code>, and ready.</p>
        <p class="text-secondary text-sm mb-6">Uploads and generation stay unavailable until their local adapters are implemented and ready.</p>
        <button type="button" class="px-4 py-2 rounded-xl bg-primary text-black font-bold">Close</button>
    `;
    const close = () => { overlay.remove(); onClose?.(); };
    modal.querySelector('button').onclick = close;
    overlay.onclick = event => { if (event.target === overlay) close(); };
    overlay.appendChild(modal);
    return overlay;
}
