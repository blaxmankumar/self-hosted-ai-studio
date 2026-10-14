'use client';

import { useState, useEffect, useCallback, useRef } from 'react';
import { ImageStudio, VideoStudio, LipSyncStudio, CinemaStudio } from 'studio';
import { getHealth, getModels, getJobs, isLocalOutputUrl } from 'studio/src/api.js';
import { configureModels } from 'studio/src/models.js';
import LocalBackendSettings from './ApiKeyModal';

const TABS = [
  { id: 'image', label: 'Image Studio' },
  { id: 'video', label: 'Video Studio' },
  { id: 'lipsync', label: 'Lip Sync' },
  { id: 'cinema', label: 'Cinema Studio' },
];
const HISTORY_KEY = 'open-higgsfield.local.v1.history';
const safeHistory = entries => Array.isArray(entries) ? entries.filter(entry =>
  entry && isLocalOutputUrl(entry.url) && ['image', 'video', 'lipsync', 'cinema'].includes(entry.type)) : [];

export default function StandaloneShell() {
  const [activeTab, setActiveTab] = useState('image');
  const [showSettings, setShowSettings] = useState(false);
  const [health, setHealth] = useState(null);
  const [catalog, setCatalog] = useState([]);
  const [connectionError, setConnectionError] = useState('');
  const [historyError, setHistoryError] = useState('');
  const [checking, setChecking] = useState(true);
  const [catalogVersion, setCatalogVersion] = useState(0);
  const [history, setHistory] = useState([]);
  const [historyLoaded, setHistoryLoaded] = useState(false);
  const [jobs, setJobs] = useState([]);
  const refreshId = useRef(0);
  const selectableCatalog = useRef('[]');

  const refresh = useCallback(async () => {
    const id = ++refreshId.current;
    setChecking(true);
    const results = await Promise.allSettled([getHealth(), getModels(), getJobs()]);
    if (id !== refreshId.current) return;
    const [healthResult, modelResult, jobsResult] = results;
    const connected = healthResult.status === 'fulfilled' && healthResult.value?.status === 'ok';
    setHealth(connected ? healthResult.value : null);
    const models = connected && modelResult.status === 'fulfilled' && Array.isArray(modelResult.value?.models)
      ? modelResult.value.models : [];
    setCatalog(models);
    configureModels(models);
    const signature = JSON.stringify(models.filter(model => model.configured && model.available));
    if (signature !== selectableCatalog.current) {
      selectableCatalog.current = signature;
      setCatalogVersion(version => version + 1);
    }
    setConnectionError(!connected ? (healthResult.reason?.message || 'The backend health response is invalid.')
      : modelResult.status === 'rejected' ? modelResult.reason.message : '');
    if (jobsResult.status === 'fulfilled') {
      setJobs(jobsResult.value.jobs);
      const completed = jobsResult.value.jobs.filter(job => job.status === 'completed' && job.url).map(job => ({
        id: job.id, url: job.url, model: job.model, prompt: job.prompt,
        type: job.type, timestamp: job.created_at, settings: job.parameters,
      }));
      setHistory(previous => {
        const merged = [...previous, ...completed.filter(entry => !previous.some(old => old.url === entry.url))];
        return safeHistory(merged).slice(0, 100);
      });
      setHistoryError('');
    } else {
      setHistoryError(jobsResult.reason?.message || 'Cannot load local job history.');
    }
    setChecking(false);
  }, []);

  useEffect(() => {
    // Retire only known old inference secrets. Existing user histories are preserved.
    try { localStorage.removeItem('muapi_key'); } catch { /* Storage can be disabled by the browser. */ }
    delete window.__MUAPI_KEY__;
    try { setHistory(safeHistory(JSON.parse(localStorage.getItem(HISTORY_KEY) || '[]'))); } catch { /* Empty history is safe. */ }
    setHistoryLoaded(true);
    refresh();
    return () => { ++refreshId.current; };
  }, [refresh]);

  useEffect(() => {
    if (!historyLoaded) return;
    try { localStorage.setItem(HISTORY_KEY, JSON.stringify(safeHistory(history))); } catch { /* Server jobs remain stored locally. */ }
  }, [history, historyLoaded]);

  const onGenerationComplete = useCallback(entry => {
    if (!isLocalOutputUrl(entry.url)) return;
    setHistory(previous => [{ ...entry, id: entry.id || Date.now().toString(), timestamp: new Date().toISOString() },
      ...previous.filter(old => old.url !== entry.url)].slice(0, 100));
    getJobs().then(data => setJobs(data.jobs)).catch(error => setHistoryError(error.message));
  }, []);
  const available = catalog.filter(model => model.configured && model.available);
  const tabHistory = history.filter(entry => entry.type === activeTab);

  return (
    <div className="h-screen bg-[#050505] flex flex-col overflow-hidden">
      <header className="flex-shrink-0 flex flex-wrap items-center justify-between gap-3 px-4 pt-4 pb-0 border-b border-white/5">
        <span className="text-white font-black text-lg tracking-wider uppercase">Open Higgsfield AI</span>
        <nav className="flex items-center gap-1" aria-label="Studios">
          {TABS.map(tab => (
            <button key={tab.id} onClick={() => setActiveTab(tab.id)}
              className={`px-4 py-2 text-sm font-medium rounded-t-lg transition-colors ${activeTab === tab.id
                ? 'bg-[#d9ff00] text-black' : 'text-white/50 hover:text-white'}`}>
              {tab.label}
            </button>
          ))}
        </nav>
        <button onClick={() => setShowSettings(true)} className="text-white/50 hover:text-white text-sm">Settings</button>
      </header>
      <div className="flex-shrink-0 px-4 py-3 border-b border-white/5 text-sm flex flex-wrap items-center gap-3" role="status" aria-live="polite">
        <span className={health ? 'text-[#d9ff00]' : 'text-amber-300'}>
          {checking ? 'Checking local backend...' : health ? 'Local backend connected' : 'Local backend unavailable'}
        </span>
        <span className="text-white/50">{available.length ? `${available.length} available model(s)` : 'No GPU worker available'}</span>
        <button onClick={refresh} disabled={checking} className="text-white/80 underline disabled:opacity-40">Retry connection</button>
        {connectionError && <span className="text-amber-300">{connectionError}</span>}
        {historyError && health && <span className="text-amber-300">History: {historyError}</span>}
        {!available.length && <p className="w-full text-xs text-white/40">Configure a permitted GPU worker in FastAPI, then retry the connection. Generation becomes available when the worker reports a ready model.</p>}
        {jobs.length > 0 && <span className="text-xs text-white/40">Local jobs: {jobs.length}; latest: {jobs[0].status}</span>}
      </div>
      <div className="flex-1 min-h-0 overflow-auto" key={catalogVersion}>
        {activeTab === 'image' && <ImageStudio onGenerationComplete={onGenerationComplete} historyItems={tabHistory} />}
        {activeTab === 'video' && <VideoStudio onGenerationComplete={onGenerationComplete} historyItems={tabHistory} />}
        {activeTab === 'lipsync' && <LipSyncStudio onGenerationComplete={onGenerationComplete} historyItems={tabHistory} />}
        {activeTab === 'cinema' && <CinemaStudio onGenerationComplete={onGenerationComplete} historyItems={tabHistory} />}
      </div>
      {showSettings && <LocalBackendSettings health={health} catalog={catalog} error={connectionError}
        checking={checking} onRetry={refresh} onClose={() => setShowSettings(false)} />}
    </div>
  );
}
