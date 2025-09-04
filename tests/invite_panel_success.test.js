/**
 * @jest-environment jsdom
 */

const fs = require('fs');
const path = require('path');

async function loadScript() {
  const code = fs
    .readFileSync(path.resolve(__dirname, '../static/js/invite_panel.js'), 'utf8')
    .replace(/^import[^\n]*\n/gm, '');
  const AsyncFunction = Object.getPrototypeOf(async function () {}).constructor;
  await new AsyncFunction(code)();
}

test('shows success toast, resets form and adds row on invite creation', async () => {
  document.body.innerHTML = `
    <form id="manualForm">
      <input id="phone" required />
      <input name="email" />
      <input name="name" required />
      <select id="host" required>
        <option value=""></option>
        <option value="H">H</option>
      </select>
      <select id="linkHost"></select>
      <select id="linkType"></select>
      <div class="photo-controls" data-prefix="p"><input type="hidden" value="img" /><input id="p_photoSource" type="hidden" /></div>
      <video id="p_preview"></video>
      <img id="p_photoPreview" />
      <button id="p_capturePhoto"></button>
      <div id="p_cameraError"></div>
      <input id="p_upload" />
      <button id="p_retake"></button>
      <button id="createBtn" type="submit"></button>
    </form>
    <button id="genLink"></button>
    <div id="linkBox"></div>
    <div id="inviteToast"><div id="inviteToastMsg"></div></div>
    <table id="inviteTable"><tbody></tbody></table>
    <button id="loadMore"></button>
  `;

  const showMock = jest.fn();
  global.bootstrap = { Toast: { getOrCreateInstance: jest.fn(() => ({ show: showMock })) } };
  global.intlTelInput = jest.fn(() => ({ isValidNumber: () => true }));
  const hostChoices = { getValue: jest.fn(() => 'H'), removeActiveItems: jest.fn() };
  const linkHostChoices = { getValue: jest.fn(() => '') };
  const linkTypeChoices = { getValue: jest.fn(() => '') };
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

  global.fetch = jest
    .fn()
    .mockResolvedValueOnce({ ok: true, json: () => Promise.resolve({ invites: [], next_cursor: null }) })
    .mockResolvedValueOnce({ ok: true, json: () => Promise.resolve({ id: 'XYZ' }) })
    .mockResolvedValue({ ok: true, json: () => Promise.resolve({ invites: [], next_cursor: null }) });
  global.validateEmail = () => true;
  global.showFieldError = jest.fn();
  global.clearFieldError = jest.fn();
  global.alert = jest.fn();

  await loadScript();

  const form = document.getElementById('manualForm');
  document.getElementById('phone').value = '9876543210';
  document.querySelector('input[name="email"]').value = 'a@b.com';
  document.querySelector('input[name="name"]').value = 'Alice';
  document.getElementById('host').value = 'H';

  form.dispatchEvent(new Event('submit'));
  await Promise.resolve();
  await Promise.resolve();

  expect(showMock).toHaveBeenCalled();
  expect(document.getElementById('inviteToastMsg').textContent).toBe('Invite created');
  expect(document.getElementById('inviteToast').className).toContain('text-bg-success');
  expect(document.getElementById('phone').value).toBe('');
  expect(document.querySelector('input[name="email"]').value).toBe('');
  expect(document.querySelector('input[name="name"]').value).toBe('');
  expect(document.getElementById('host').value).toBe('');
  expect(hostChoices.removeActiveItems).toHaveBeenCalled();
  const row = document.querySelector('#inviteTable tbody tr');
  expect(row).not.toBeNull();
  expect(row.querySelector('td').textContent).toBe('XYZ');
});
