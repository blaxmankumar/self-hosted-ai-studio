// Backward-compatible source entry point; all transport is local.
export * from './localApi.js';
export { LocalClient as MuapiClient, localApi as muapi } from './localApi.js';
