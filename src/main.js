import './style.css';
import { Header } from './components/Header.js';
import { getHealth, getModels } from './lib/localApi.js';
import { configureModels, t2iModels, t2vModels } from './lib/models.js';
import { clearLegacyProviderCredentials } from './lib/localStorage.js';

clearLegacyProviderCredentials();
const app = document.querySelector('#app');
const pages = { image: 'Image', video: 'Video', lipsync: 'Lip Sync', cinema: 'Cinema Studio' };
let page = 'image';
let backend = { phase: 'checking', message: 'Checking the local backend…', models: [] };
let renderVersion = 0;
let checking = false;
let lastCatalog = '';
let renderedKey = '';

app.replaceChildren(Header(navigate));
const statusBar = document.createElement('div');
statusBar.className = 'local-backend-status';
statusBar.setAttribute('role', 'status');
statusBar.setAttribute('aria-live', 'polite');
app.appendChild(statusBar);
const contentArea = document.createElement('main');
contentArea.id = 'content-area';
contentArea.className = 'flex-1 relative w-full overflow-hidden flex flex-col bg-app-bg';
app.appendChild(contentArea);

function availableForPage() {
  if (backend.phase !== 'online') return false;
  if (page === 'image' || page === 'cinema') return t2iModels.length > 0;
  if (page === 'video') return t2vModels.length > 0;
  // Lip sync requires validated media uploads; the foundation returns 501.
  return false;
}

function unavailablePanel() {
  const panel = document.createElement('section');
  panel.className = 'local-unavailable';
  const label = document.createElement('p');
  label.className = 'local-eyebrow';
  label.textContent = `${pages[page]} · Local workspace`;
  const title = document.createElement('h1');
  title.textContent = backend.phase === 'checking' ? 'Connecting to your local backend'
    : backend.phase === 'desktop' ? 'Open the local browser workspace'
    : backend.phase === 'offline' ? 'Local backend unavailable'
    : 'Local model unavailable';
  const description = document.createElement('p');
  description.className = 'local-description';
  description.textContent = backend.phase === 'online'
    ? page === 'lipsync'
      ? 'Lip sync needs a configured local model and validated media uploads. These integrations are not ready yet.'
      : `No local ${page === 'video' ? 'video' : 'image'} model is ready for generation. A local model adapter must be implemented and configured with model paths in backend/.env before generation can begin.`
    : backend.message;
  const retry = document.createElement('button');
  retry.type = 'button';
  retry.className = 'local-retry';
  retry.textContent = 'Retry connection';
  retry.disabled = checking || backend.phase === 'desktop';
  retry.onclick = () => checkBackend(true);
  panel.append(label, title, description, retry);
  if (backend.phase === 'online') {
    const type = page === 'video' ? 'video' : page === 'lipsync' ? 'lipsync' : 'image';
    const reasons = [...new Set(backend.models.filter(model => model.type === type && !model.available)
      .map(model => model.reason).filter(reason => typeof reason === 'string' && reason))];
    if (reasons.length) {
      const detail = document.createElement('p');
      detail.className = 'local-note';
      detail.textContent = reasons.join(' ');
      panel.appendChild(detail);
    }
    const note = document.createElement('p');
    note.className = 'local-note';
    note.textContent = 'No API key is needed. Model choices are supplied by your local backend.';
    panel.appendChild(note);
  }
  return panel;
}

async function renderPage(force = false) {
  const key = `${page}:${backend.phase}:${lastCatalog}`;
  statusBar.textContent = backend.phase === 'online'
    ? `Local backend connected · ${t2iModels.length + t2vModels.length} ready image/video models`
    : backend.message;
  statusBar.dataset.state = backend.phase;
  if (!force && key === renderedKey) return;
  renderedKey = key;
  const version = ++renderVersion;
  contentArea.replaceChildren();
  if (!availableForPage()) {
    contentArea.appendChild(unavailablePanel());
    return;
  }
  const module = page === 'image' ? await import('./components/ImageStudio.js')
    : page === 'video' ? await import('./components/VideoStudio.js')
    : await import('./components/CinemaStudio.js');
  if (version !== renderVersion) return;
  const create = module.ImageStudio || module.VideoStudio || module.CinemaStudio;
  contentArea.appendChild(create());
}

function navigate(nextPage) {
  if (!(nextPage in pages)) return;
  page = nextPage;
  void renderPage();
}

async function checkBackend(force = false) {
  if (checking) return;
  if (window.location.protocol === 'file:') {
    backend = {
      phase: 'desktop', models: [],
      message: 'This packaged desktop window has no local API proxy. Run the backend and frontend, then open http://127.0.0.1:5173 in a browser.',
    };
    configureModels([]);
    await renderPage(true);
    return;
  }
  checking = true;
  if (force) {
    backend = { ...backend, phase: 'checking', message: 'Checking the local backend…' };
    await renderPage(true);
  }
  try {
    const [health, catalog] = await Promise.all([getHealth({ timeoutMs: 5000 }), getModels({ timeoutMs: 5000 })]);
    if (health?.status !== 'ok' || !Array.isArray(catalog?.models)) {
      throw new Error('The local backend returned an unexpected health or model response.');
    }
    configureModels(catalog.models);
    lastCatalog = JSON.stringify(catalog.models);
    backend = { phase: 'online', message: 'Local backend connected', models: catalog.models };
  } catch (error) {
    configureModels([]);
    lastCatalog = '';
    backend = { phase: 'offline', models: [], message: error.message || 'Cannot reach the local backend. Start FastAPI and retry.' };
  } finally {
    checking = false;
    await renderPage(force);
  }
}

window.addEventListener('navigate', async event => {
  if (event.detail?.page === 'settings') {
    const { SettingsModal } = await import('./components/SettingsModal.js');
    document.body.appendChild(SettingsModal());
  } else {
    navigate(event.detail?.page);
  }
});
void renderPage();
void checkBackend();
if (window.location.protocol !== 'file:') {
  window.setInterval(() => { void checkBackend(); }, 20000);
}
