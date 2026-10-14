const assert = require('node:assert/strict');
const React = require('react');
const { renderToStaticMarkup } = require('react-dom/server');

// Run after npm.cmd run build:studio. Render every preserved studio with the
// real empty registry; catches missing state variables on inactive tabs too.
const { configureModels } = require('../packages/studio/dist/models.js');
configureModels([]);
for (const name of ['ImageStudio', 'VideoStudio', 'LipSyncStudio', 'CinemaStudio']) {
  const Studio = require(`../packages/studio/dist/components/${name}.js`).default;
  const html = renderToStaticMarkup(React.createElement(Studio, { historyItems: [] }));
  assert.ok(html.length > 100, `${name} rendered no content`);
  assert.ok(html.includes('disabled'), `${name} must disable inference when no model is available`);
  assert.ok(!html.includes('Muapi API Key'), `${name} contains a retired key prompt`);
  console.log(`PASS: ${name} renders with an empty local model registry.`);
}

// A saved backend result must be selectable after reload, before another image
// is generated. The URL below is a transport fixture, not a generated image.
const ImageStudio = require('../packages/studio/dist/components/ImageStudio.js').default;
const output = '/api/local/outputs/12345678-1234-1234-1234-123456789abc/result.png';
const historyHtml = renderToStaticMarkup(React.createElement(ImageStudio, {
  historyItems: [{ id: 'history-fixture', url: output, prompt: 'Stored image fixture' },
    { id: 'remote-fixture', url: 'https://example.test/result.png' }],
}));
assert.ok(historyHtml.includes('View generated image 1'), 'Saved image history is inaccessible before generation');
assert.ok(historyHtml.includes(output), 'Saved image thumbnail is missing');
assert.ok(!historyHtml.includes('https://example.test/result.png'), 'Remote history media was rendered');
console.log('PASS: ImageStudio restores safe saved image history before another generation.');
