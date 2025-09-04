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

function commonStubs() {
  global.intlTelInput = jest.fn(() => ({ isValidNumber: () => true }));
  const hostChoices = { getValue: () => '', removeActiveItems: jest.fn() };
  const linkHostChoices = { getValue: () => '' };
  const linkTypeChoices = { getValue: () => '' };
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
  window.PhotoCapture = function () {
    this.init = jest.fn();
  };
  global.validateEmail = () => true;
}

beforeEach(() => {
  jest.resetModules();
  document.body.innerHTML = '';
});

test('validates fields before creating invite', async () => {
  document.body.innerHTML = `
    <form id="manualForm">
      <input id="phone" required />
      <input name="email" />
      <input name="name" required />
      <select id="host" required></select>
      <select id="linkHost"></select>
      <select id="linkType"></select>
      <div class="photo-controls" data-prefix="p"><input type="hidden" /><input id="p_photoSource" type="hidden" /></div>
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
    <table id="inviteTable"><tbody></tbody></table>
    <button id="loadMore"></button>
  `;
  commonStubs();
  global.fetch = jest.fn().mockResolvedValue({ ok: true, json: () => Promise.resolve({ invites: [], next_cursor: null }) });
  global.showFieldError = jest.fn();
  global.clearFieldError = jest.fn();
  await loadScript();
  const initialCalls = global.fetch.mock.calls.length;
  document.getElementById('manualForm').dispatchEvent(new Event('submit'));
  await Promise.resolve();
  await Promise.resolve();
  expect(global.fetch.mock.calls.length).toBe(initialCalls);
  expect(global.showFieldError).toHaveBeenCalled();
});

test('submits JSON payload to /api/invites', async () => {
  document.body.innerHTML = `
    <form id="manualForm">
      <input id="phone" required value="1234567890" />
      <input name="email" value="test@example.com" />
      <input name="name" required value="Test User" />
      <select name="role"><option value="2" selected>Manager</option></select>
      <input id="expiry" value="2024-01-01T00:00:00.000Z" />
      <select id="host" required><option value="H" selected>H</option></select>
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
    <table id="inviteTable"><tbody></tbody></table>
    <button id="loadMore"></button>
  `;
  global.intlTelInput = jest.fn(() => ({ isValidNumber: () => true }));
  const hostChoices = { getValue: () => 'H', removeActiveItems: jest.fn() };
  const linkHostChoices = { getValue: () => '' };
  const linkTypeChoices = { getValue: () => '' };
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
  const fetchMock = jest.fn().mockResolvedValue({ ok: true, json: () => Promise.resolve({ inviteId: '1' }) });
  global.fetch = fetchMock;
  global.showFieldError = jest.fn();
  global.clearFieldError = jest.fn();
  global.validateEmail = () => true;
  global.alert = jest.fn();
  await loadScript();
  document.getElementById('manualForm').dispatchEvent(new Event('submit'));
  await Promise.resolve();
  await Promise.resolve();
  const call = fetchMock.mock.calls.find(c => c[0] === '/api/invites');
  expect(call).toBeTruthy();
  const opts = call[1];
  expect(opts.method).toBe('POST');
  expect(opts.headers['Content-Type']).toBe('application/json');
  expect(JSON.parse(opts.body)).toEqual({
    inviteeEmail: 'test@example.com',
    fullName: 'Test User',
    roleId: 2,
    expiresAt: '2024-01-01T00:00:00.000Z',
  });
});

test('table filtering passes parameters', async () => {
  document.body.innerHTML = `
    <form id="manualForm">
      <input id="phone" />
      <input name="email" />
      <select id="host"></select>
      <select id="linkHost"></select>
      <select id="linkType"></select>
      <div class="photo-controls" data-prefix="p"><input type="hidden" /><input id="p_photoSource" type="hidden" /></div>
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
    <select id="typeFilter"><option value="manual">manual</option></select>
    <select id="statusFilter"><option value="created">created</option></select>
    <select id="daysFilter"><option value="7">7</option></select>
    <table id="inviteTable"><tbody></tbody></table>
    <button id="loadMore"></button>
  `;
  commonStubs();
  const fetchMock = jest.fn().mockResolvedValue({ ok: true, json: () => Promise.resolve({ invites: [], next_cursor: null }) });
  global.fetch = fetchMock;
  global.showFieldError = jest.fn();
  global.clearFieldError = jest.fn();
  await loadScript();
  const typeFilter = document.getElementById('typeFilter');
  const statusFilter = document.getElementById('statusFilter');
  const daysFilter = document.getElementById('daysFilter');
  typeFilter.value = 'manual';
  statusFilter.value = 'created';
  daysFilter.value = '7';
  typeFilter.dispatchEvent(new Event('change'));
  await new Promise(res => setTimeout(res, 0));
  const url = fetchMock.mock.calls[fetchMock.mock.calls.length - 1][0];
  expect(url).toContain('invite_source=manual');
  expect(url).toContain('status=created');
  expect(url).toContain('days=7');
});

test('row actions handle failure', async () => {
  document.body.innerHTML = `
    <form id="manualForm">
      <input id="phone" />
      <input name="email" />
      <select id="host"></select>
      <select id="linkHost"></select>
      <select id="linkType"></select>
      <div class="photo-controls" data-prefix="p"><input type="hidden" /><input id="p_photoSource" type="hidden" /></div>
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
    <table id="inviteTable"><tbody></tbody></table>
    <button id="loadMore"></button>
  `;
  commonStubs();
  const fetchMock = jest.fn()
    .mockResolvedValueOnce({ ok: true, json: () => Promise.resolve({ invites: [], next_cursor: null }) })
    .mockResolvedValue({ ok: false });
  global.fetch = fetchMock;
  global.alert = jest.fn();
  global.showFieldError = jest.fn();
  global.clearFieldError = jest.fn();
  await loadScript();
  await window.approve('abc');
  expect(global.alert).toHaveBeenCalledWith('Failed to approve invite');
});

test('enables create button when fields valid', async () => {
  document.body.innerHTML = `
    <form id="manualForm">
      <input id="phone" required />
      <input name="email" />
      <input name="name" required />
      <select id="host" required><option value="">Select</option><option value="H">H</option></select>
      <select id="linkHost"></select>
      <select id="linkType"></select>
      <div class="photo-controls" data-prefix="p"><input type="hidden" /><input id="p_photoSource" type="hidden" /></div>
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
    <table id="inviteTable"><tbody></tbody></table>
    <button id="loadMore"></button>
  `;
  const form = document.getElementById('manualForm');
  form.reportValidity = jest.fn(() => {
    return Array.from(form.querySelectorAll('[required]')).every(f => !!f.value);
  });
  commonStubs();
  global.fetch = jest.fn().mockResolvedValue({ ok: true, json: () => Promise.resolve({ invites: [], next_cursor: null }) });
  global.showFieldError = jest.fn();
  global.clearFieldError = jest.fn();
  await loadScript();
  const btn = document.getElementById('createBtn');
  expect(btn.disabled).toBe(true);
  document.getElementById('phone').value = '123';
  document.getElementsByName('name')[0].value = 'A';
  const host = document.getElementById('host');
  host.value = 'H';
  host.dispatchEvent(new Event('change'));
  document.getElementById('phone').dispatchEvent(new Event('input'));
  document.getElementsByName('name')[0].dispatchEvent(new Event('input'));
  await Promise.resolve();
  expect(btn.disabled).toBe(false);
});
