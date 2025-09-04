import { validateEmail, showFieldError, clearFieldError } from './validation.js';
import { PhotoUploader } from './photo_uploader.js';

const form = document.getElementById('pubForm');
const nameField = document.getElementById('name');
const phoneField = document.getElementById('phone');
const emailField = document.getElementById('email');
const typeField = document.getElementById('visitor_type');
const companyField = document.getElementById('company');
const purposeField = document.getElementById('purpose_text');
const hostField = document.getElementById('host');
const visitField = document.getElementById('visit_time');
const controls = document.querySelector('.photo-controls');
// Retrieve prefix for unique element IDs
const prefix = controls?.dataset.prefix ?? '';
const getEl = (s) => document.getElementById(`${prefix}_${s}`);
const photoField = getEl('photoInput');
const photoSource = getEl('photoSource');
const msgBox = document.getElementById('msg');
const noPhoto = getEl('noPhoto');
const reasonBlock = getEl('noPhotoReasonBlock');
const reasonInput = getEl('noPhotoReason');

const phoneInput = intlTelInput(phoneField, {
  initialCountry: 'in',
  utilsScript: 'https://cdn.jsdelivr.net/npm/intl-tel-input@18.1.1/build/js/utils.js'
});
flatpickr('#visit_time', { enableTime: true });

// Camera
const captureBtn = getEl('capturePhoto');
const cameraMsg = getEl('cameraError');
const brightness = getEl('brightness');
if (location.protocol !== 'https:' && location.hostname !== 'localhost') {
  cameraMsg.textContent = 'Camera access requires HTTPS. Please use https://';
}
const photoUploader = new PhotoUploader({
  videoEl: getEl('preview'),
  previewEl: getEl('photoPreview'),
  captureBtn,
  uploadBtn: getEl('uploadPhoto'),
  uploadInput: getEl('upload'),
  resetBtn: getEl('retake'),
  changeBtn: getEl('changePhoto'),
  brightnessInput: getEl('brightness'),
  noPhotoCheckbox: noPhoto,
  onCapture: (data, source) => {
    if (photoField) photoField.value = data;
    if (photoSource) photoSource.value = source || 'none';
  }
});

noPhoto?.addEventListener('change', () => {
  if (noPhoto.checked) {
    reasonBlock?.classList.remove('d-none');
    if (photoSource) photoSource.value = 'none';
  } else {
    reasonBlock?.classList.add('d-none');
    if (reasonInput) reasonInput.value = '';
  }
});

// Ensure camera options and face models are loaded before use
await photoUploader.init();

[nameField, phoneField, emailField, typeField, hostField, visitField, companyField, purposeField].forEach(field => {
  field.addEventListener('input', () => clearFieldError(field));
});

form.addEventListener('submit', async e => {
  e.preventDefault();
  let valid = true;
  if (!nameField.value.trim()) {
    showFieldError(nameField, 'Name is required');
    valid = false;
  }
  if (!phoneInput.isValidNumber()) {
    showFieldError(phoneField, 'Invalid phone number');
    valid = false;
  }
  if (emailField.value && !validateEmail(emailField.value)) {
    showFieldError(emailField, 'Invalid email address');
    valid = false;
  }
  if (!typeField.value.trim()) {
    showFieldError(typeField, 'Visitor type is required');
    valid = false;
  }
  if (!hostField.value.trim()) {
    showFieldError(hostField, 'Host is required');
    valid = false;
  }
  if (!visitField.value.trim()) {
    showFieldError(visitField, 'Visit time is required');
    valid = false;
  }
  if (!companyField.value.trim()) {
    showFieldError(companyField, 'Company is required');
    valid = false;
  }
  const purposeVal = purposeField.value.trim();
  if (!purposeVal) {
    showFieldError(purposeField, 'Purpose is required');
    valid = false;
  } else if (purposeVal.length < 3 || purposeVal.length > 120) {
    showFieldError(purposeField, 'Purpose must be 3-120 characters');
    valid = false;
  }
  if (!noPhoto?.checked && !photoField?.value.trim()) {
    cameraMsg.textContent = 'Photo is required';
    valid = false;
  } else {
    cameraMsg.textContent = '';
  }
  if (!valid) return;

  const data = new FormData(form);
  if (noPhoto?.checked) {
    data.append('no_photo', 'on');
  }
  const r = await fetch('/invite/form/submit', { method: 'POST', body: data });
  const d = await r.json().catch(() => ({}));
  if (r.ok && d.saved) {
    if (d.visitor_id) {
      window.location.href = `/invite/thanks?visitor_id=${encodeURIComponent(d.visitor_id)}`;
    } else {
      msgBox.innerHTML = '<div class="alert alert-success">Submitted. Check your email for confirmation or contact reception on arrival.</div>';
      form.reset();
      if (photoField) photoField.value = '';
      photoUploader.reset();
    }
  } else if (d.errors) {
    msgBox.innerHTML = '';
    Object.entries(d.errors).forEach(([field, message]) => {
      const input = form.querySelector(`[name="${field}"]`);
      if (input) {
        showFieldError(input, message);
      } else if (field === 'photo') {
        cameraMsg.textContent = message;
      } else {
        msgBox.innerHTML = `<div class="alert alert-danger">${message}</div>`;
      }
    });
  } else {
    msgBox.innerHTML = '<div class="alert alert-danger">Error</div>';
  }
});
