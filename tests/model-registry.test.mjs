import test from 'node:test';
import assert from 'node:assert/strict';
import { configureModels, t2iModels, i2iModels, t2vModels, imageLipSyncModels, getModelById } from '../packages/studio/src/models.js';

test('only configured and available models enter studio selectors', () => {
  const originalReference = t2iModels;
  configureModels([
    { id: 'absent', name: 'Absent', type: 'image', configured: false, available: false, capabilities: ['text-to-image'] },
    { id: 'lying', name: 'Unconfigured', type: 'image', configured: false, available: true, capabilities: ['text-to-image'] },
    { id: 'offline', name: 'Offline', type: 'image', configured: true, available: false, capabilities: ['text-to-image'] },
    { id: 'test-local', name: 'Test fixture only', type: 'image', configured: true, available: true, capabilities: ['text-to-image'], inputs: {} },
  ]);
  assert.equal(t2iModels, originalReference);
  assert.deepEqual(t2iModels.map(m => m.id), ['test-local']);
  assert.equal(i2iModels.length, 0);
  assert.equal(getModelById('absent'), undefined);
  configureModels([]);
  assert.equal(t2iModels.length, 0);
});

test('capabilities and feature type decide which studio can use a model', () => {
  configureModels([
    { id: 'edit-only', name: 'Edit fixture', type: 'image', configured: true, available: true, capabilities: ['image-to-image'] },
    { id: 'video-only', name: 'Video fixture', type: 'video', configured: true, available: true, capabilities: ['text-to-video'] },
    { id: 'lip-only', name: 'Lip fixture', type: 'lipsync', configured: true, available: true, capabilities: ['image-audio-to-video'] },
  ]);
  assert.equal(t2iModels.length, 0);
  assert.deepEqual(i2iModels.map(m => m.id), ['edit-only']);
  assert.deepEqual(t2vModels.map(m => m.id), ['video-only']);
  assert.deepEqual(imageLipSyncModels.map(m => m.id), ['lip-only']);
  configureModels(null);
  assert.equal(t2vModels.length, 0);
});
