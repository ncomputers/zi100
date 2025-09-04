import { validateEmail, showFieldError, clearFieldError } from './validation.js';
import { PhotoUploader } from './photo_uploader.js';

const manualForm = document.getElementById('manualForm');
const publicForm = document.getElementById('pubForm');
const form = manualForm || publicForm;
const toastEl = document.getElementById('inviteToast');
const toastMsg = document.getElementById('inviteToastMsg');
const showToast = (msg, variant = 'success') => {
  if (!toastEl) { alert(msg); return; }
  toastEl.className = `toast text-bg-${variant} border-0`;
  toastMsg.textContent = msg;
  bootstrap.Toast.getOrCreateInstance(toastEl).show();
};

if (form) {
  const createBtn = document.getElementById('createBtn');
  let isSubmitting = false;
  const updateCreateBtn = () => {
    if (createBtn) {
      createBtn.disabled = !form.reportValidity() || isSubmitting;
    }
  };
  const phoneField = document.getElementById('phone');
  const emailField = form.querySelector('input[name="email"]');
  const nameField = form.querySelector('input[name="name"]');
  const expiryField = document.getElementById('expiry');
  const roleField = form.querySelector('select[name="role"]');
  const phoneInput = intlTelInput(phoneField, {
    initialCountry: 'in',
    utilsScript: 'https://cdn.jsdelivr.net/npm/intl-tel-input@18.1.1/build/js/utils.js'
  });

  phoneField.addEventListener('input', () => { clearFieldError(phoneField); updateCreateBtn(); });
  emailField.addEventListener('input', () => { clearFieldError(emailField); updateCreateBtn(); });

  if (manualForm) {
    const requiredFields = manualForm.querySelectorAll('[required]');
    requiredFields.forEach(f => {
      f.addEventListener('input', () => { clearFieldError(f); updateCreateBtn(); });
      f.addEventListener('change', () => { clearFieldError(f); updateCreateBtn(); });
    });
    updateCreateBtn();
    const hostSel = new Choices('#host', {
      removeItemButton: true,
      duplicateItemsAllowed: false,
      searchEnabled: true,
      placeholderValue: 'Select Host',
      placeholder: true
    });
    const linkHostSel = new Choices('#linkHost', {
      removeItemButton: true,
      duplicateItemsAllowed: false,
      searchEnabled: true,
      placeholderValue: 'Select Host',
      placeholder: true
    });
    const linkTypeSel = new Choices('#linkType', {
      removeItemButton: true,
      duplicateItemsAllowed: false,
      searchEnabled: true,
      placeholderValue: 'Visitor Type',
      placeholder: true
    });
    const updateLinkBtn = () => {
      const host = linkHostSel.getValue(true);
      const vtype = linkTypeSel.getValue(true);
      document.getElementById('genLink').disabled = !(host && vtype);
    };
    document.getElementById('linkHost').addEventListener('change', () => {
      clearFieldError(document.getElementById('linkHost'));
      updateLinkBtn();
    });
    document.getElementById('linkType').addEventListener('change', () => {
      clearFieldError(document.getElementById('linkType'));
      updateLinkBtn();
    });
    updateLinkBtn();
    flatpickr('#visit_time', { enableTime: true, minDate: 'today' });
    flatpickr('#expiry', { enableTime: true, minDate: 'today' });
    new Choices('#purpose');

    const controls = document.querySelector('.photo-controls');
    const prefix = controls?.dataset.prefix ?? '';
    const getEl = (s) => document.getElementById(`${prefix}_${s}`);
    const photoInput = controls?.querySelector('input[type="hidden"]');
    const cameraMsg = getEl('cameraError');
    const noPhotoCb = getEl('noPhoto');
    if (location.protocol !== 'https:' && location.hostname !== 'localhost') {
      if (cameraMsg) cameraMsg.textContent = 'Camera access requires HTTPS. Please use https://';
    }
    const captureBtn = getEl('capturePhoto');
    const uploadInput = getEl('upload');
    const retakeBtn = getEl('retake');
    let photoUploader;
    if (captureBtn && uploadInput && retakeBtn) {
      photoUploader = new PhotoUploader({
        videoEl: getEl('preview'),
        previewEl: getEl('photoPreview'),
        captureBtn,
        uploadBtn: getEl('uploadPhoto'),
        uploadInput,
        resetBtn: retakeBtn,
        changeBtn: getEl('changePhoto'),
        onCapture: (data) => {
          if (photoInput) photoInput.value = data;
          updateCreateBtn();
        }
      });
      await photoUploader.init();
      captureBtn.addEventListener('click', () => photoUploader.capture());
      uploadInput.addEventListener('change', (e) => photoUploader.handleUpload(e));
      retakeBtn.addEventListener('click', () => photoUploader?.reset());
      noPhotoCb?.addEventListener('change', () => {
        if (noPhotoCb.checked) {
          if (cameraMsg) cameraMsg.textContent = '';
          photoUploader?.reset();
          if (photoInput) photoInput.value = '';
        }
        updateCreateBtn();
      });
    }


    phoneField.addEventListener('change', async e => {
      const ph = e.target.value.replace(/\D/g, '');
      if (ph.length < 3) return;
      const r = await fetch('/invite/lookup?phone=' + ph);
      if (r.ok) {
        const d = await r.json();
        if (d.name) { document.querySelector('input[name="name"]').value = d.name; }
        if (d.email) { emailField.value = d.email; }
        document.getElementById('lookupInfo').textContent = d.last_id ? `ID: ${d.last_id} Visits: ${d.visits}` : '';
      }
    });

    manualForm.addEventListener('submit', async e => {
      e.preventDefault();
      let valid = true;
      requiredFields.forEach(field => {
        if (!field.value) {
          showFieldError(field, 'This field is required');
          valid = false;
        }
      });
      if (!phoneInput.isValidNumber()) {
        showFieldError(phoneField, 'Invalid phone number');
        valid = false;
      }
      if (emailField.value && !validateEmail(emailField.value)) {
        showFieldError(emailField, 'Invalid email address');
        valid = false;
      }
      if (!hostSel.getValue(true)) {
        showFieldError(document.getElementById('host'), 'Host is required');
        valid = false;
      }
      if (!noPhotoCb?.checked && !photoInput?.value.trim()) {
        if (cameraMsg) cameraMsg.textContent = 'Photo is required';
        valid = false;
      } else if (cameraMsg) {
        cameraMsg.textContent = '';
      }
      if (!valid) return;
      const payload = {
        inviteeEmail: emailField.value,
        fullName: nameField?.value,
        roleId: Number(roleField?.value),
        expiresAt: expiryField?.value ? new Date(expiryField.value).toISOString() : null,
      };
      const btn = document.getElementById('createBtn');
      btn.disabled = true;

      try {
        const r = await fetch('/api/invites', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(payload),
        });
        if (r.ok) {
          await r.json().catch(() => ({}));
          showToast('Invite created', 'success');
          e.target.reset();
          hostSel.removeActiveItems();
          if (photoInput) photoInput.value = '';
          photoUploader?.reset();
        } else {
          const data = await r.json();
          if (data.errors) {
            for (const [field, messages] of Object.entries(data.errors)) {
              if (field === 'non_field_errors') {
                messages.forEach(m => showToast(m, 'danger'));
              } else {
                const el = form.querySelector(`[name="${field}"]`);
                if (el) messages.forEach(m => showFieldError(el, m));
                else messages.forEach(m => showToast(m, 'danger'));
              }
            }
          } else {
            showToast('Failed to create invite', 'danger');
          }
        }
      } catch (err) {
        showToast(err.message || 'Failed to create invite', 'danger');
      } finally {
        isSubmitting = false;
        updateCreateBtn();
      }
    });

    document.getElementById('genLink').addEventListener('click', async () => {
      const hostEl = document.getElementById('linkHost');
      const typeEl = document.getElementById('linkType');
      const host = linkHostSel.getValue(true);
      const vtype = linkTypeSel.getValue(true);
      let valid = true;
      if (!host) { showFieldError(hostEl, 'Host is required'); valid = false; }
      if (!vtype) { showFieldError(typeEl, 'Visitor type is required'); valid = false; }
      if (!valid) return;
      const data = new FormData();
      data.set('host', host);
      data.set('visitor_type', vtype);
      const btn = document.getElementById('genLink');
      btn.disabled = true;
      try {
        const r = await fetch('/invite/create?link=1', { method: 'POST', body: data });
        const box = document.getElementById('linkBox');
        if (r.ok) {
          const d = await r.json();
          const fullLink = d.link.startsWith('http') ? d.link : `${location.origin}${d.link}`;
          box.innerHTML = `
            <div class="input-group mb-2">
              <input class="form-control" value="${fullLink}" readonly>
              <button class="btn btn-outline-secondary" type="button" id="copyLink">Copy</button>
            </div>
            <div id="qrBox" class="text-center"></div>`;
          box.querySelector('#copyLink').addEventListener('click', () => {
            navigator.clipboard.writeText(fullLink);
          });
          const qrBox = box.querySelector('#qrBox');
          if (window.QRCode) {
            const cvs = document.createElement('canvas');
            qrBox.appendChild(cvs);
            QRCode.toCanvas(cvs, fullLink, { width: 128 }, err => {});
          }
          loadTable(true);
        } else {
          let msg = 'Failed to generate link';
          try {
            const err = await r.json();
            msg = err.error || err.detail || msg;
          } catch {
            const txt = await r.text();
            msg = txt || msg;
          }
          box.innerHTML = `<div class="alert alert-danger">${msg}</div>`;
        }
      } catch (err) {
        document.getElementById('linkBox').innerHTML = `<div class="alert alert-danger">${err.message || 'Failed to generate link'}</div>`;
      } finally {
        updateLinkBtn();
      }
    });

    const typeFilter = document.getElementById('typeFilter');
    const statusFilter = document.getElementById('statusFilter');
    const daysFilter = document.getElementById('daysFilter');
    [typeFilter, statusFilter, daysFilter].forEach(el => {
      el?.addEventListener('change', () => loadTable(true));
    });
    let cursor = 0;
    const limit = 20;
    async function loadTable(reset = false, newInvite = null) {
      if (reset) {
        cursor = 0;
        document.querySelector('#inviteTable tbody').innerHTML = '';
      }
      const tb = document.querySelector('#inviteTable tbody');
      if (newInvite) {
        const tr = document.createElement('tr');
        tr.innerHTML = `<td>${newInvite.id}</td><td>${newInvite.name || ''}</td><td>${newInvite.phone || ''}</td><td>${newInvite.email || ''}</td><td>${newInvite.visitor_type || ''}</td><td>${newInvite.company || ''}</td><td>${newInvite.host || ''}</td><td>${newInvite.visit_time || ''}</td><td>${newInvite.status}</td><td>${new Date(newInvite.ts * 1000).toLocaleString()}</td><td><button class='btn btn-sm btn-success me-1' onclick="approve('${newInvite.id}')">✅</button><button class='btn btn-sm btn-warning me-1' onclick="hold('${newInvite.id}')">⏸️</button><button class='btn btn-sm btn-danger' onclick="rejectInvite('${newInvite.id}')">❌</button></td>`;
        tb.appendChild(tr);
        cursor = 1;
      }
      const params = new URLSearchParams({ limit, cursor });
      if (typeFilter?.value) params.append('invite_source', typeFilter.value);
      if (statusFilter?.value) params.append('status', statusFilter.value);
      if (daysFilter?.value && daysFilter.value !== 'all') params.append('days', daysFilter.value);
      const r = await fetch(`/invite/list?${params.toString()}`);
      if (!r.ok) return;
      const data = await r.json();
      const rows = data.invites || [];
      rows.forEach(it => {
        const tr = document.createElement('tr');
        tr.innerHTML = `<td>${it.id}</td><td>${it.name || ''}</td><td>${it.phone || ''}</td><td>${it.email || ''}</td><td>${it.visitor_type || ''}</td><td>${it.company || ''}</td><td>${it.host || ''}</td><td>${it.visit_time || ''}</td><td>${it.status}</td><td>${new Date(it.ts * 1000).toLocaleString()}</td><td><button class='btn btn-sm btn-success me-1' onclick="approve('${it.id}')">✅</button><button class='btn btn-sm btn-warning me-1' onclick="hold('${it.id}')">⏸️</button><button class='btn btn-sm btn-danger' onclick="rejectInvite('${it.id}')">❌</button></td>`;
        tb.appendChild(tr);
      });
      cursor = data.next_cursor ?? null;
      if (rows.length < limit || !cursor) {
        document.getElementById('loadMore').classList.add('d-none');
      } else {
        document.getElementById('loadMore').classList.remove('d-none');
      }
    }

    async function approve(id) {
      const r = await fetch('/invite/approve/' + id, { method: 'PUT' });
      if (r.ok) {
        const d = await r.json().catch(() => ({}));
        alert(d.gate_id ? `Gate pass ${d.gate_id} created` : 'Invite approved');
        loadTable(true);
      } else {
        alert('Failed to approve invite');
      }
    }
    async function hold(id) { await fetch('/invite/hold/' + id, { method: 'PUT' }); loadTable(true); }
    async function rejectInvite(id) { await fetch('/invite/reject/' + id, { method: 'PUT' }); loadTable(true); }

    document.getElementById('loadMore').addEventListener('click', () => loadTable());
    loadTable();

    window.approve = approve;
    window.hold = hold;
    window.rejectInvite = rejectInvite;
  } else {
    form.addEventListener('submit', async e => {
      e.preventDefault();
      let valid = true;
      if (phoneField.value && !phoneInput.isValidNumber()) {
        showFieldError(phoneField, 'Invalid phone number');
        valid = false;
      }
      if (emailField.value && !validateEmail(emailField.value)) {
        showFieldError(emailField, 'Invalid email address');
        valid = false;
      }
      if (!valid) return;
      const data = new FormData(form);
      const r = await fetch('/invite/form/submit', { method: 'POST', body: data });
      const msg = document.getElementById('msg');
      if (r.ok) {
        msg.innerHTML = '<div class="alert alert-success">Submitted</div>';
        form.reset();
      } else {
        msg.innerHTML = '<div class="alert alert-danger">Error</div>';
      }
    });
  }
}
