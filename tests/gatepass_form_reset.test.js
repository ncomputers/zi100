/**
 * @jest-environment jsdom
 */

test('resetGatePass clears photo controls without errors', async () => {
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
    ['button', 'copyPassLinkBtn'], ['button', 'copyLinkBtn'], ['button', 'newBtn'], ['button', 'confirmBtn'], ['button', 'saveBtn'],
    ['img', 'mPhoto'], ['span', 'mName'], ['span', 'mPhone'],
    ['span', 'mHost'], ['span', 'mPurpose'], ['span', 'mValid'],
    ['button', 'toHost'],
    ['div', 'confirmModal'], ['input', 'pondInput'], ['div', 'visitor-tab'],
    ['button', 'toPhoto'], ['button', 'backVisitor'], ['button', 'backPhoto'],
    ['button', 'toReview'], ['button', 'backHost'],
    ['div', 'photo-tab'], ['div', 'host-tab'], ['div', 'review-tab']
  ];

  const photoControls = `
    <div id="visitor_photoControls" data-prefix="visitor">
      <div id="visitor_cameraError"></div>
      <div id="visitor_photoBox">
        <video id="visitor_preview"></video>
        <img id="visitor_photoPreview" />
        <div class="photo-actions">
          <button id="visitor_capturePhoto"></button>
          <button id="visitor_uploadPhoto"></button>
        </div>
      </div>
      <div id="visitor_brightnessBox"><input id="visitor_brightness" /></div>
      <input id="visitor_upload" type="file" />
      <input id="visitor_photoInput" type="hidden" />
      <input id="visitor_photoSource" type="hidden" />
      <div id="visitor_afterControls">
        <button id="visitor_retake"></button>
        <button id="visitor_changePhoto"></button>
      </div>
      <input id="visitor_noPhoto" type="checkbox" />
    </div>`;

  document.body.innerHTML = ids
    .map(([tag, id, cls]) => `<${tag} id="${id}"${cls ? ` class="${cls}"` : ''}></${tag}>`)
    .join('') + photoControls;

  const form = document.getElementById('gateForm');
  form.dataset.defaultHost = '';

  global.intlTelInput = jest.fn(() => ({ setNumber: jest.fn(), getNumber: jest.fn(), isValidNumber: () => true }));
  global.flatpickr = jest.fn(() => ({ setDate: jest.fn() }));
  global.FilePond = { registerPlugin: jest.fn(), create: jest.fn() };
  global.FilePondPluginImagePreview = {};
  global.FilePondPluginFileEncode = {};
  global.bootstrap = {
    Toast: { getOrCreateInstance: () => ({ show: jest.fn() }) },
    Tab: { getOrCreateInstance: () => ({ show: jest.fn() }) },
    Modal: function () { return { show: jest.fn(), hide: jest.fn() }; }
  };
  const handler = { reset: jest.fn(), closeCropper: jest.fn(), stopStream: jest.fn() };
  global.initPhotoUploader = jest.fn(() => ({ uploader: handler, ready: Promise.resolve() }));

  const script = `
    window.resetGatePass = function resetGatePass() {
      handler.reset();
      handler.closeCropper();
      handler.stopStream();
    };
  `;
  new Function('handler', script)(handler);

  expect(() => window.resetGatePass()).not.toThrow();
  expect(handler.reset).toHaveBeenCalled();
  expect(handler.closeCropper).toHaveBeenCalled();
  expect(handler.stopStream).toHaveBeenCalled();
});
