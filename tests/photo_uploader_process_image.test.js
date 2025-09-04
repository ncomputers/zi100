/**
 * @jest-environment jsdom
 */

const fs = require('fs');
const path = require('path');

async function loadPhotoUploader() {
  let code = fs.readFileSync(path.resolve(__dirname, '../static/js/photo_uploader.js'), 'utf8');
  code = code.replace(/^export\s+/gm, '');
  const AsyncFunction = Object.getPrototypeOf(async function () {}).constructor;
  return await new AsyncFunction(code + '; return { PhotoUploader };')();
}

test('processImage invokes openCropper and returns a promise', async () => {
  const { PhotoUploader } = await loadPhotoUploader();
  const uploader = new PhotoUploader({
    captureBtn: document.createElement('button'),
    uploadBtn: document.createElement('button'),
  });
  uploader.modelsLoaded = false;
  const spy = jest.spyOn(uploader, 'openCropper').mockResolvedValue(true);
  const result = uploader.processImage('data:image/png;base64,test');
  expect(spy).toHaveBeenCalled();
  expect(result).toBeTruthy();
  await result;
});

test.each([
  ['image/png', 'file.png'],
  ['image/jpeg', 'file.jpg'],
])('handleUpload waits for cropper on %s', async (type, name) => {
  const { PhotoUploader } = await loadPhotoUploader();
  document.body.innerHTML = '<input id="u" type="file"><img id="p"><div id="err"></div>';
  const hidden = document.createElement('input');
  const uploader = new PhotoUploader({
    previewEl: document.getElementById('p'),
    captureBtn: document.createElement('button'),
    uploadBtn: document.createElement('button'),
    uploadInput: document.getElementById('u'),
    hiddenInput: hidden,
    errorBox: document.getElementById('err'),
  });
  uploader.updateCropPreview = jest.fn();
  uploader.useImage = jest.fn().mockImplementation(() => {
    hidden.value = 'set';
    return Promise.resolve(true);
  });
  global.bootstrap = { Modal: class { show() {} hide() {} } };
  global.Cropper = function (img, opts) {
    setTimeout(opts.ready, 0);
    this.getCroppedCanvas = () => document.createElement('canvas');
  };
  global.URL.createObjectURL = () => 'blob:test';
  global.URL.revokeObjectURL = () => {};
  const file = new File(['foo'], name, { type });
  const evt = { target: { files: [file], value: 'x' } };
  const p = uploader.handleUpload(evt);
  uploader.cropImg.onload();
  expect(hidden.value).toBe('');
  document.querySelector('#pcUse').click();
  await p;
  expect(hidden.value).not.toBe('');
});

test('openCropper resolves false and keeps listener when useImage fails', async () => {
  const { PhotoUploader } = await loadPhotoUploader();
  document.body.innerHTML = '';
  const uploader = new PhotoUploader({
    previewEl: document.createElement('img'),
    captureBtn: document.createElement('button'),
    uploadBtn: document.createElement('button'),
  });
  global.bootstrap = { Modal: class { show() {} hide() {} } };
  global.Cropper = function (img, opts) {
    setTimeout(opts.ready, 0);
    this.getCroppedCanvas = () => document.createElement('canvas');
  };
  uploader.useImage = jest
    .fn()
    .mockResolvedValueOnce(false)
    .mockResolvedValueOnce(true);
  const p = uploader.openCropper('foo');
  uploader.cropImg.onload();
  const useBtn = uploader.cropModal.querySelector('#pcUse');
  useBtn.click();
  await expect(p).resolves.toBe(false);
  expect(uploader.useImage).toHaveBeenCalledTimes(1);
  useBtn.click();
  await new Promise((res) => setTimeout(res, 0));
  expect(uploader.useImage).toHaveBeenCalledTimes(2);
});
