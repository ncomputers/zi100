/**
 * @jest-environment jsdom
 */

const fs = require('fs');
const path = require('path');

async function loadScript() {
  const code = fs
    .readFileSync(path.resolve(__dirname, '../static/js/invite_public.js'), 'utf8')
    .replace(/^import[^\n]*\n/gm, '');
  const AsyncFunction = Object.getPrototypeOf(async function () {}).constructor;
  await new AsyncFunction(code)();
}

function baseDom() {
  document.body.innerHTML = `
    <form id="pubForm">
      <input id="name" />
      <input id="phone" />
      <input id="email" />
      <select id="visitor_type"></select>
      <input id="company" />
      <input id="purpose_text" />
      <input id="host" />
      <input id="visit_time" />
      <div class="mb-2 form-check text-start">
        <input class="form-check-input" type="checkbox" id="invite_noPhoto" />
        <label for="invite_noPhoto"></label>
      </div>
      <div class="text-center photo-controls" data-prefix="invite" id="invite_photoControls">
        <div id="invite_cameraError"></div>
        <div id="invite_photoBox" class="photo-placeholder">
          <video id="invite_preview" class="d-none"></video>
          <img id="invite_photoPreview" class="d-none" />
          <div class="photo-actions">
            <button id="invite_capturePhoto" type="button"></button>
            <button id="invite_uploadPhoto" type="button"></button>
          </div>
        </div>
        <input type="file" id="invite_upload" />
        <input type="hidden" id="invite_photoInput" />
        <input type="hidden" id="invite_photoSource" />
        <div id="invite_afterControls" class="d-none">
          <button id="invite_retake" type="button"></button>
          <button id="invite_changePhoto" type="button"></button>
        </div>
      </div>
      <div class="mt-2 d-none" id="invite_noPhotoReasonBlock">
        <input id="invite_noPhotoReason" name="no_photo_reason" />
      </div>
    </form>
    <div id="msg"></div>
  `;
}

function commonStubs(uploaderImpl = function () {}) {
  global.intlTelInput = jest.fn(() => ({ isValidNumber: () => true }));
  global.flatpickr = jest.fn();
  global.validateEmail = jest.fn(() => true);
  global.showFieldError = jest.fn();
  global.clearFieldError = jest.fn();
  global.PhotoUploader = uploaderImpl;
}

test('initializes PhotoUploader with capture and upload controls', async () => {
  baseDom();
  const calls = [];
  function MockUploader(opts) {
    calls.push(opts);
    this.init = jest.fn(() => Promise.resolve());
  }
  commonStubs(MockUploader);
  await loadScript();
  expect(calls[0].captureBtn.id).toBe('invite_capturePhoto');
  expect(calls[0].uploadBtn.id).toBe('invite_uploadPhoto');
  // simulate capture
  calls[0].onCapture('img');
  expect(document.getElementById('invite_photoInput').value).toBe('img');
});

test('shows waiver reason when no-photo checked', async () => {
  baseDom();
  function MockUploader() {
    this.init = jest.fn(() => Promise.resolve());
  }
  commonStubs(MockUploader);
  await loadScript();
  const box = document.getElementById('invite_noPhotoReasonBlock');
  const chk = document.getElementById('invite_noPhoto');
  chk.checked = true;
  chk.dispatchEvent(new Event('change'));
  expect(box.classList.contains('d-none')).toBe(false);
  chk.checked = false;
  chk.dispatchEvent(new Event('change'));
  expect(box.classList.contains('d-none')).toBe(true);
});

