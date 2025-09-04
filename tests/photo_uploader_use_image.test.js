/**
 * @jest-environment jsdom
 */

const fs = require('fs');
const path = require('path');

async function loadPhotoUploader() {
  let code = fs.readFileSync(
    path.resolve(__dirname, '../static/js/photo_uploader.js'),
    'utf8',
  );
  code = code.replace(/^export\s+/gm, '');
  const AsyncFunction = Object.getPrototypeOf(async function () {}).constructor;
  return await new AsyncFunction(code + '; return { PhotoUploader };')();
}

test('useImage populates hidden input and preview', async () => {
  const { PhotoUploader } = await loadPhotoUploader();
  global.Cropper = function () {};

  const video = document.createElement('video');
  const img = document.createElement('img');
  const hidden = document.createElement('input');
  hidden.type = 'hidden';

  const uploader = new PhotoUploader({
    videoEl: video,
    previewEl: img,
    captureBtn: document.createElement('button'),
    uploadBtn: document.createElement('button'),
    uploadInput: document.createElement('input'),
    hiddenInput: hidden,
    onCapture: jest.fn(),
    startBtn: document.createElement('button'),
    stopBtn: document.createElement('button'),
    brightnessInput: document.createElement('input'),
    resetBtn: document.createElement('button'),
    changeBtn: document.createElement('button'),
  });

  uploader.closeCropper = jest.fn();

  const canvas = {
    toBlob: (cb) => cb(new Blob(['x'], { type: 'image/jpeg' })),
  };
  uploader.cropper = { getCroppedCanvas: () => canvas };
  uploader.applyAdjustments = jest.fn((c) => c);

  await new Promise((resolve) => {
    global.FileReader = class {
      constructor() {
        this.onloadend = null;
        this.onerror = null;
      }
      readAsDataURL() {
        this.result = 'data:image/jpeg;base64,abc';
        if (this.onloadend) this.onloadend();
        resolve();
      }
    };
    uploader.useImage();
  });

  expect(hidden.value).toBe('data:image/jpeg;base64,abc');
  expect(img.src).toBe('data:image/jpeg;base64,abc');
  expect(uploader.onCapture).toHaveBeenCalledWith('data:image/jpeg;base64,abc');
});

test('clampCanvas limits longest side to 1024', async () => {
  const { PhotoUploader } = await loadPhotoUploader();
  const uploader = new PhotoUploader({
    captureBtn: document.createElement('button'),
    uploadBtn: document.createElement('button'),
  });
  const origCreate = document.createElement.bind(document);
  document.createElement = (tag) => {
    if (tag === 'canvas') {
      return { width: 0, height: 0, getContext: () => ({ drawImage: jest.fn() }) };
    }
    return origCreate(tag);
  };
  const canvas = { width: 2048, height: 512 };
  const result = uploader.clampCanvas(canvas);
  expect(result.width).toBe(1024);
  expect(result.height).toBe(256);
  document.createElement = origCreate;
});

  test('capture rejects images exceeding max size', async () => {
    const { PhotoUploader } = await loadPhotoUploader();
    global.URL.createObjectURL = () => 'blob:test';
    global.URL.revokeObjectURL = () => {};
    const video = document.createElement('video');
    video.videoWidth = 100;
    video.videoHeight = 100;
    const origGetContext = HTMLCanvasElement.prototype.getContext;
    HTMLCanvasElement.prototype.getContext = () => ({ drawImage: jest.fn() });
    const hidden = document.createElement('input');
    hidden.type = 'hidden';
  const uploader = new PhotoUploader({
    videoEl: video,
    previewEl: document.createElement('img'),
    captureBtn: document.createElement('button'),
    uploadBtn: document.createElement('button'),
    hiddenInput: hidden,
    errorBox: document.createElement('div'),
    stopBtn: document.createElement('button'),
    startBtn: document.createElement('button'),
  });
  uploader.processImage = jest.fn().mockResolvedValue(false);
  uploader.showError = jest.fn();
  uploader.stopStream = jest.fn();
  uploader.maxSize = 1;
    uploader.applyAdjustments = jest.fn(() => ({
      toBlob: (cb) => cb(new Blob(['xx'], { type: 'image/jpeg' })),
    }));
    await uploader.capture();
    expect(uploader.showError).toHaveBeenCalledWith('Image too large');
    expect(hidden.value).toBe('');
    HTMLCanvasElement.prototype.getContext = origGetContext;
  });

