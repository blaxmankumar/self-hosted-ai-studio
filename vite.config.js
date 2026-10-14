import { defineConfig } from 'vite';

// Use the root PostCSS/Tailwind configuration shared with the Next frontend.
const localProxy = {
    '/api/local': {
        target: 'http://127.0.0.1:8000',
        rewrite: (path) => path.replace(/^\/api\/local/, '')
    }
};

export default defineConfig({
    base: './',
    server: {
        host: '127.0.0.1',
        port: 5173,
        strictPort: true,
        proxy: localProxy
    },
    preview: {
        host: '127.0.0.1',
        port: 5173,
        strictPort: true,
        proxy: localProxy
    }
});
