/**
 * @jest-environment jsdom
 */

test('shows field errors and re-enables button on invite creation failure', async () => {
  document.body.innerHTML = `
    <form id="manualForm">
      <input id="phone" />
      <input name="email" />
      <input name="name" />
      <select id="host"></select>
      <select id="linkHost"></select>
      <select id="linkType"></select>
      <input id="visit_time" />
      <input id="expiry" />
      <select id="purpose"></select>
      <div class="photo-controls" data-prefix="p">
        <input type="hidden" value="img" />
        <input id="p_photoSource" type="hidden" />
      </div>
      <video id="p_preview"></video>
      <img id="p_photoPreview" />
      <button id="p_capturePhoto"></button>
      <div id="p_cameraError"></div>
      <input id="p_upload" />
      <button id="p_retake"></button>
      <div id="lookupInfo"></div>
      <button id="createBtn" type="submit">Create Invite</button>
    </form>
    <button id="genLink"></button>
    <div id="linkBox"></div>
    <table id="inviteTable"><tbody></tbody></table>
    <button id="loadMore"></button>
  `;

  global.intlTelInput = jest.fn(() => ({ isValidNumber: () => true }));
  const hostChoices = { getValue: () => 'H', removeActiveItems: jest.fn() };
  const linkHostChoices = { getValue: () => 'H' };
  const linkTypeChoices = { getValue: () => 'Official' };
  global.Choices = jest.fn((sel) => {
    if (sel === '#host') return hostChoices;
    if (sel === '#linkHost') return linkHostChoices;
    if (sel === '#linkType') return linkTypeChoices;
    return { getValue: () => '' };
  });
  global.PhotoUploader = class {
    constructor() {
      this.init = jest.fn(() => Promise.resolve());
      this.startCam = jest.fn(() => Promise.resolve());
      this.reset = jest.fn();
    }
  };
  global.flatpickr = jest.fn();
  window.PhotoCapture = function () { this.init = jest.fn(); };

  const fetchMock = jest.fn()
    .mockResolvedValueOnce({ ok: true, json: () => Promise.resolve({ invites: [], next_cursor: null }) });
  let resolveFetch;
  fetchMock.mockReturnValueOnce(new Promise(res => { resolveFetch = res; }));
  global.fetch = fetchMock;
  global.validateEmail = () => true;
  global.showFieldError = jest.fn();
  global.clearFieldError = jest.fn();
  global.alert = jest.fn();

  const fs = require('fs');
  const path = require('path');
  const code = fs
    .readFileSync(path.resolve(__dirname, '../static/js/invite_panel.js'), 'utf8')
    .replace(/^import[^\n]*\n/gm, '');
  // Execute invite_panel.js without the ESM imports
  const AsyncFunction = Object.getPrototypeOf(async function () {}).constructor;
  await new AsyncFunction(code)();

  const form = document.getElementById('manualForm');
  const btn = document.getElementById('createBtn');
  form.dispatchEvent(new Event('submit'));
  await Promise.resolve();
  expect(btn.disabled).toBe(true);
  resolveFetch({ ok: false, json: () => Promise.resolve({ errors: { name: ['required'], non_field_errors: ['error message'] } }) });
  await Promise.resolve();
  await Promise.resolve();
  const nameInput = document.querySelector('input[name="name"]');
  expect(global.showFieldError).toHaveBeenCalledWith(nameInput, 'required');
  expect(global.alert).toHaveBeenCalledWith('error message');
  expect(btn.disabled).toBe(false);
});
