// Helper UI components for face engine interactions.

// previewFace routine
export function previewFace(fileInput, imgEl) {
  const file = fileInput.files[0];
  if (!file) return;
  const reader = new FileReader();
  reader.onload = e => {
    imgEl.src = e.target.result;
  };
  reader.readAsDataURL(file);
}

// listCameras routine
export async function listCameras(selectEl) {
  try {
    if (!navigator.mediaDevices?.enumerateDevices) throw new Error('unsupported');
    const devices = await navigator.mediaDevices.enumerateDevices();
    selectEl.innerHTML = '';
    devices.filter(d => d.kind === 'videoinput').forEach((d, idx) => {
      const opt = document.createElement('option');
      opt.value = d.deviceId;
      opt.textContent = d.label || `Camera ${idx + 1}`;
      selectEl.appendChild(opt);
    });
  } catch (err) {
    alert('Camera access denied or not supported. Please upload an image instead.');
  }
}

// drawBox routine
export function drawBox(ctx, box, color = 'lime') {
  const [x1, y1, x2, y2] = box;
  ctx.strokeStyle = color;
  ctx.lineWidth = 2;
  ctx.strokeRect(x1, y1, x2 - x1, y2 - y1);
}
