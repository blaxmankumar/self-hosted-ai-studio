// Compatibility entry point for the preserved legacy studio components.
// Every request is handled by the same-origin, provider-neutral local API.
import {
    getHealth, getModels, getJobs, getJob, submitGeneration, pollForResult,
    generateImage, generateI2I, generateVideo, generateI2V, processLipSync, uploadFile,
} from '../../packages/studio/src/api.js';

export { getHealth, getModels, getJobs, getJob };
export class LocalClient {
    generateImage(params) { return generateImage(params); }
    generateI2I(params) { return generateI2I(params); }
    generateVideo(params) { return generateVideo(params); }
    generateI2V(params) { return generateI2V(params); }
    processLipSync(params) { return processLipSync(params); }
    uploadFile(file) { return uploadFile(file); }
    pollForResult(jobId, options) { return pollForResult(jobId, options); }
    async processV2V(params) {
        const job = await submitGeneration('video', params);
        return job.status === 'completed' ? job : pollForResult(job.id);
    }
}

export const localApi = new LocalClient();
