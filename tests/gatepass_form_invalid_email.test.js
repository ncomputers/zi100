/**
 * @jest-environment jsdom
 */

test('invalid email blocks navigation to photo step', async () => {
  const ids = [
    ['form', 'gateForm'], ['div', 'toast'], ['div', 'toastMsg'],
    ['input', 'inviteId'], ['input', 'vName'], ['datalist', 'vNameList'],
    ['input', 'vPhone'], ['input', 'vEmail'], ['select', 'vType'],
    ['input', 'vPurpose'], ['input', 'vCompany'], ['input', 'vValid'],
    ['input', 'hName'], ['input', 'hDept'], ['input', 'needApproval'],
    ['div', 'approverBox'], ['input', 'approverEmail'],
    ['img', 'prevPhoto'],
    ['span', 'pName'], ['span', 'pPhone'], ['span', 'pEmail'],
    ['span', 'pType'], ['span', 'pCompany'], ['span', 'pHost'],
    ['span', 'pPurpose'], ['span', 'pGate'], ['span', 'pValid'], ['span', 'pStatus'],
    ['div', 'qrBox'],
    ['button', 'printBtn'], ['button', 'pdfBtn'], ['button', 'viewBtn'],
    ['button', 'copyLinkBtn'], ['button', 'copyPassLinkBtn'], ['button', 'newBtn'], ['button', 'confirmBtn'], ['button', 'saveBtn'],
    ['img', 'mPhoto'], ['span', 'mName'], ['span', 'mPhone'],
    ['span', 'mHost'], ['span', 'mPurpose'], ['span', 'mValid'],
    ['input', 'uploadPhoto'], ['input', 'captured'], ['button', 'toHost'],
    ['div', 'photoSource'], ['input', 'srcUpload'], ['input', 'srcCamera'],
    ['div', 'uploadControls', 'upload-controls'], ['div', 'cameraControls', 'camera-controls'],
    ['video', 'cam'], ['div', 'cropContainer'], ['img', 'cropImg'],
    ['button', 'captureBtn'], ['button', 'startCam'], ['button', 'stopCam'], ['button', 'useImage'],
    ['div', 'confirmModal'], ['input', 'pondInput'], ['div', 'visitor-tab'],
    ['button', 'toPhoto'], ['button', 'backVisitor'], ['button', 'backPhoto'],
    ['button', 'toReview'], ['button', 'backHost'],
    ['div', 'photo-tab'], ['div', 'host-tab'], ['div', 'review-tab']
  ];

  document.body.innerHTML = ids
    .map(([tag, id, cls]) => `<${tag} id="${id}"${cls ? ` class="${cls}"` : ''}></${tag}>`)
    .join('');

  const form = document.getElementById('gateForm');
  form.dataset.defaultHost = '';

  const vName = document.getElementById('vName');
  const vPhone = document.getElementById('vPhone');
  const vEmail = document.getElementById('vEmail');
  const vType = document.getElementById('vType');
  const vPurpose = document.getElementById('vPurpose');
  const vValid = document.getElementById('vValid');

  vName.value = 'Visitor';
  vPhone.value = '1';
  vEmail.value = 'not-an-email';
  vType.value = 't';
  vPurpose.value = 'p';
  vValid.value = '2024-01-01 00:00';

  global.intlTelInput = jest.fn(() => ({
    setNumber: jest.fn(),
    getNumber: jest.fn(),
    isValidNumber: () => true
  }));
  global.flatpickr = jest.fn(() => ({ setDate: jest.fn() }));
  global.FilePond = { registerPlugin: jest.fn(), create: jest.fn() };
  global.FilePondPluginImagePreview = {};
  global.FilePondPluginFileEncode = {};
  const showTab = jest.fn();
  global.bootstrap = {
    Toast: { getOrCreateInstance: () => ({ show: jest.fn() }) },
    Tab: { getOrCreateInstance: () => ({ show: showTab }) },
    Modal: function () { return { show: jest.fn(), hide: jest.fn() }; }
  };
  global.initPhotoUploader = jest.fn(() => ({ uploader: {}, ready: Promise.resolve() }));
  global.validateEmail = () => false;
  global.showFieldError = jest.fn();
  global.clearFieldError = jest.fn();

  const fs = require('fs');
  const path = require('path');
  let code = fs.readFileSync(path.resolve(__dirname, '../static/js/gatepass_form.js'), 'utf8');
  code = code.replace(/^import[\s\S]*?;\n/gm, '');
  code = code.replace(/export\s+async\s+function initGatepassForm/, 'async function initGatepassForm');
  new Function(code)();
  await Promise.resolve();

  document.getElementById('toPhoto').click();

  expect(showFieldError).toHaveBeenCalledWith(vEmail, 'Invalid email');
  expect(showTab).not.toHaveBeenCalled();
});

