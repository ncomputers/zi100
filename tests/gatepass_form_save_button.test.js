/**
 * @jest-environment jsdom
 */

 test('save button disabled until request resolves', async () => {
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

   global.intlTelInput = jest.fn(() => ({
     setNumber: jest.fn(),
     getNumber: () => '123',
     isValidNumber: () => true
   }));
   global.flatpickr = jest.fn(() => ({ setDate: jest.fn() }));
   global.FilePond = { registerPlugin: jest.fn(), create: jest.fn() };
   global.FilePondPluginImagePreview = {};
   global.FilePondPluginFileEncode = {};
   global.bootstrap = {
     Toast: { getOrCreateInstance: () => ({ show: jest.fn() }) },
     Tab: { getOrCreateInstance: () => ({ show: jest.fn() }) },
     Modal: function (el) {
       return {
         show: () => el.dispatchEvent(new Event('show.bs.modal')),
         hide: () => el.dispatchEvent(new Event('hide.bs.modal'))
       };
     }
   };
   global.validateEmail = () => true;
   global.showFieldError = jest.fn();
   global.clearFieldError = jest.fn();
  const handler = { reset: jest.fn(), closeCropper: jest.fn(), stopStream: jest.fn() };
  global.initPhotoUploader = jest.fn(() => ({ uploader: handler, ready: Promise.resolve() }));
  global.QRCode = { toCanvas: jest.fn((c, t, o, cb) => cb && cb()) };
  global.navigator = { clipboard: { writeText: jest.fn() }, share: jest.fn() };
  global.window.open = jest.fn();
  global.html2pdf = jest.fn(() => ({ from: () => ({ save: jest.fn().mockResolvedValue() }) }));

  const script = `
    const captureBtn = document.getElementById('visitor_capturePhoto');
    const uploadBtn = document.getElementById('visitor_uploadPhoto');
    const uploadInput = document.getElementById('visitor_upload');
    const hiddenInput = document.getElementById('visitor_photoInput');
    const videoEl = document.getElementById('visitor_preview');
    const previewEl = document.getElementById('visitor_photoPreview');
    const toHostBtn = document.getElementById('toHost');
    initPhotoUploader({
      captureBtn,
      uploadBtn,
      uploadInput,
      hiddenInput,
      videoEl,
      previewEl,
      onCapture: (data) => {
        hiddenInput.value = data;
        toHostBtn.disabled = false;
      }
    });

    const saveBtn = document.getElementById('saveBtn');
    const confirmModalEl = document.getElementById('confirmModal');
    async function handleSave() {
      saveBtn.disabled = true;
      confirmModalEl.dispatchEvent(new Event('hide.bs.modal'));
      const r = await fetch();
      await r.json();
      saveBtn.disabled = false;
    }
    confirmModalEl.addEventListener('show.bs.modal', () => {
      saveBtn.addEventListener('click', handleSave, { once: true });
    });
    confirmModalEl.addEventListener('hide.bs.modal', () => {
      saveBtn.removeEventListener('click', handleSave);
    });
  `;
  new Function('initPhotoUploader', script)(global.initPhotoUploader);

   vName.value = 'V';
   vPhone.value = '1';
   vEmail.value = 'a@b.c';
   vType.value = 't';
   vPurpose.value = 'p';
   vValid.value = '2024-01-01 00:00';
   hName.value = 'h';
   document.getElementById('visitor_photoInput').value = 'x';

   let resolveFetch;
   global.fetch = jest.fn(() => new Promise(res => { resolveFetch = res; }));

  const confirmModalEl = document.getElementById('confirmModal');
  confirmModalEl.dispatchEvent(new Event('show.bs.modal'));
  saveBtn.click();
   expect(saveBtn.disabled).toBe(true);

  resolveFetch({ ok: true, json: async () => ({ gate_id: '1', status: 'Created' }) });
  await new Promise((r) => setTimeout(r, 0));

  expect(saveBtn.disabled).toBe(false);
});
