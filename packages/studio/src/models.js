// Available models are discovered from the local backend, never from a paid-provider catalog.
// Keep stable array references for existing studio helper imports.
export const t2iModels = [];
export const t2vModels = [];
export const i2iModels = [];
export const i2vModels = [];
export const v2vModels = [];
export const lipsyncModels = [];
export const imageLipSyncModels = [];
export const videoLipSyncModels = [];

export function configureModels(catalog = []) {
    const available = (Array.isArray(catalog) ? catalog : []).filter(model =>
        model?.configured === true && model?.available === true &&
        typeof model.id === 'string' && typeof model.name === 'string');
    const supports = (model, capability) => Array.isArray(model.capabilities) && model.capabilities.includes(capability);
    const replace = (target, models) => target.splice(0, target.length, ...models);
    replace(t2iModels, available.filter(m => m.type === 'image' && supports(m, 'text-to-image')));
    replace(i2iModels, available.filter(m => m.type === 'image' && supports(m, 'image-to-image')));
    replace(t2vModels, available.filter(m => m.type === 'video' && supports(m, 'text-to-video')));
    replace(i2vModels, available.filter(m => m.type === 'video' && supports(m, 'image-to-video')));
    replace(v2vModels, available.filter(m => m.type === 'video' && supports(m, 'video-to-video')));
    const lip = available.filter(m => m.type === 'lipsync');
    replace(imageLipSyncModels, lip.filter(m => supports(m, 'image-audio-to-video')).map(m => ({ ...m, category: 'image' })));
    replace(videoLipSyncModels, lip.filter(m => supports(m, 'video-audio-to-video')).map(m => ({ ...m, category: 'video' })));
    replace(lipsyncModels, [...imageLipSyncModels, ...videoLipSyncModels]);
}

export const getModelById = id => t2iModels.find(m => m.id === id);
export const getVideoModelById = id => t2vModels.find(m => m.id === id);
export const getI2IModelById = id => i2iModels.find(m => m.id === id);
export const getI2VModelById = id => i2vModels.find(m => m.id === id);
export const getV2VModelById = id => v2vModels.find(m => m.id === id);
export const getLipSyncModelById = id => lipsyncModels.find(m => m.id === id);
const options = (model, key, fallback = []) => model?.inputs?.[key]?.enum || fallback;
const resolutions = model => options(model, 'resolution', options(model, 'quality'));
const durations = model => {
    const duration = model?.inputs?.duration;
    if (duration?.enum) return duration.enum;
    if (duration?.minValue !== undefined && duration.maxValue !== undefined && duration.step > 0) {
        const result = [];
        for (let value = duration.minValue; value <= duration.maxValue && result.length < 100; value += duration.step) result.push(value);
        return result;
    }
    return duration?.default !== undefined ? [duration.default] : [];
};
export const getAspectRatiosForModel = id => options(getModelById(id), 'aspect_ratio', ['1:1', '16:9', '9:16']);
export const getAspectRatiosForVideoModel = id => options(getVideoModelById(id), 'aspect_ratio', ['16:9', '9:16', '1:1']);
export const getAspectRatiosForI2IModel = id => options(getI2IModelById(id), 'aspect_ratio', ['1:1', '16:9', '9:16']);
export const getAspectRatiosForI2VModel = id => options(getI2VModelById(id), 'aspect_ratio', ['16:9', '9:16', '1:1']);
export const getDurationsForModel = id => durations(getVideoModelById(id));
export const getDurationsForI2VModel = id => durations(getI2VModelById(id));
export const getResolutionsForModel = id => resolutions(getModelById(id));
export const getResolutionsForVideoModel = id => resolutions(getVideoModelById(id));
export const getResolutionsForI2IModel = id => resolutions(getI2IModelById(id));
export const getResolutionsForI2VModel = id => resolutions(getI2VModelById(id));
export const getResolutionsForLipSyncModel = id => resolutions(getLipSyncModelById(id));
export const getQualityFieldForModel = id => getModelById(id)?.inputs?.resolution ? 'resolution' : getModelById(id)?.inputs?.quality ? 'quality' : null;
export const getQualityFieldForI2IModel = id => getI2IModelById(id)?.inputs?.resolution ? 'resolution' : getI2IModelById(id)?.inputs?.quality ? 'quality' : null;
export const getMaxImagesForI2IModel = id => getI2IModelById(id)?.maxImages || 1;
export const getModesForModel = id => options([...t2vModels, ...i2vModels].find(m => m.id === id), 'mode');
