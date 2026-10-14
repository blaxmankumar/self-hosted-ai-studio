import { SettingsModal } from './SettingsModal.js';

// Compatibility entry point: local inference has no provider authentication.
export function AuthModal() {
    const modal = SettingsModal();
    document.body.appendChild(modal);
    return modal;
}
