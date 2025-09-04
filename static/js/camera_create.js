import { showFieldError, clearFieldError } from './validation.js';

export function initCameraForm() {
  const form = document.getElementById('cameraForm');
  if (!form) return;

  const nameInput = document.getElementById('name');
  const urlInput = document.getElementById('url');
  const previewBtn = document.getElementById('testPreview');
  const saveBtn = document.getElementById('saveBtn');
  const saveActivateBtn = document.getElementById('saveActivateBtn');
  const previewImg = document.getElementById('previewImg');
  const previewLog = document.getElementById('previewLog');
  const modal = new bootstrap.Modal(document.getElementById('previewModal'));

  function getPayload() {
    return {
      name: nameInput.value.trim(),
      url: urlInput.value.trim(),
      type: document.getElementById('type').value,
      profile: document.getElementById('profile').value,
      orientation: document.getElementById('orientation').value,
      resolution: document.getElementById('resolution').value,
      transport: document.getElementById('transport').value,
      ppe: document.getElementById('ppe').checked,
      counting: document.getElementById('inout_count').checked,
      reverse: document.getElementById('reverse').checked,
      show: document.getElementById('show').checked,
    };
  }

  function validate() {
    let ok = true;
    if (!nameInput.value.trim()) {
      showFieldError(nameInput, 'Required');
      ok = false;
    } else {
      clearFieldError(nameInput);
    }
    if (!urlInput.value.trim()) {
      showFieldError(urlInput, 'Required');
      ok = false;
    } else {
      clearFieldError(urlInput);
    }
    return ok;
  }

  async function submit(activate = false) {
    if (!validate()) return;
    const payload = getPayload();
    if (activate) payload.enabled = true;
    const camId = form.dataset.camId;
    const url = camId ? `/cameras/${camId}` : '/cameras';
    const method = camId ? 'PUT' : 'POST';
    try {
      const res = await fetch(url, {
        method,
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });
      if (res.ok) {
        window.location.href = '/cameras';
      } else {
        const err = await res.json().catch(() => ({}));
        alert(err.error || 'Failed to save');
      }
    } catch (e) {
      console.error('Save failed', e);
      alert('Failed to save');
    }
  }

  async function preview() {
    if (!validate()) return;
    previewImg.removeAttribute('src');
    previewLog.textContent = '';
    try {
      const r = await fetch('/api/cameras/test', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ url: urlInput.value.trim() }),
      });
      const d = await r.json();
      if (r.ok && d.notes) {
        previewImg.src = d.notes;
      } else {
        previewLog.textContent = d.error || 'Preview failed';
      }
    } catch (e) {
      console.error('Preview failed', e);
      previewLog.textContent = 'Preview failed';
    }
    modal.show();
  }

  previewBtn?.addEventListener('click', preview);
  saveBtn?.addEventListener('click', () => submit(false));
  saveActivateBtn?.addEventListener('click', () => submit(true));
}

initCameraForm();
