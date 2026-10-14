'use client';

// Preserve the former modal import path while retiring key collection.
export default function LocalBackendSettings({ health, catalog = [], error, checking, onRetry, onClose }) {
  return (
    <div className="fixed inset-0 bg-black/80 flex items-center justify-center z-50 px-4" role="dialog" aria-modal="true" aria-labelledby="backend-settings-title">
      <div className="bg-[#111] border border-white/10 rounded-2xl p-8 w-full max-w-lg max-h-[85vh] overflow-auto">
        <h2 id="backend-settings-title" className="text-white font-bold text-xl mb-4">Local backend settings</h2>
        <p className="text-white/60 text-sm mb-3">The studio connects through <code>/api/local</code> to your FastAPI backend. GPU worker connection settings stay on the backend.</p>
        <p className="text-white/50 text-sm mb-4">Set <code>LOCAL_BACKEND_URL</code> in the frontend environment to your loopback FastAPI server (default <code>http://127.0.0.1:8000</code>), then restart Next.js.</p>
        <p className="text-white/50 text-sm mb-4">Configure the GPU worker URL and access token in the FastAPI environment. A ready worker makes its supported models available here.</p>
        <p className="text-sm text-[#d9ff00] mb-4">{health ? 'Backend connected' : 'Backend unavailable'}</p>
        {error && <p className="text-amber-300 text-sm mb-4">{error}</p>}
        <ul className="space-y-3 mb-6">
          {catalog.map(model => <li key={model.id} className="text-sm text-white/70">
            <span className="font-semibold">{model.name}</span> - {model.configured && model.available ? 'Available' : 'Unavailable'}
            {model.reason && <p className="text-xs text-white/40 mt-1">{model.reason}</p>}
          </li>)}
          {!catalog.length && <li className="text-sm text-white/40">No model catalog is available. Start the backend and retry.</li>}
        </ul>
        <div className="flex gap-3">
          <button onClick={onRetry} disabled={checking} className="flex-1 py-2 rounded-lg bg-[#d9ff00] text-black disabled:opacity-40">{checking ? 'Checking...' : 'Retry connection'}</button>
          <button onClick={onClose} className="flex-1 py-2 rounded-lg bg-white/5 text-white hover:bg-white/10">Close</button>
        </div>
      </div>
    </div>
  );
}
