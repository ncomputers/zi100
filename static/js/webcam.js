// Real-time webcam face search and UI helpers
const video = document.getElementById('webcam');
const labelEl = document.getElementById('matchLabel');
const mergeBtn = document.getElementById('mergeBtn');
const newBtn = document.getElementById('newBtn');
let threshold = parseFloat(labelEl?.dataset?.threshold || '0.95');

async function startCamera() {
  try {
    const stream = await navigator.mediaDevices.getUserMedia({ video: true });
    video.srcObject = stream;
  } catch (err) {
    console.error('Camera access denied', err);
  }
}

async function searchFrame() {
  if (video.readyState !== 4) return;
  const canvas = document.createElement('canvas');
  canvas.width = video.videoWidth;
  canvas.height = video.videoHeight;
  const ctx = canvas.getContext('2d');
  ctx.drawImage(video, 0, 0);
  const blob = await new Promise((resolve) => canvas.toBlob(resolve, 'image/jpeg'));
  const form = new FormData();
  form.append('image', blob, 'frame.jpg');
  form.append('threshold', String(threshold));
  const res = await fetch('/face/search', { method: 'POST', body: form });
  const data = await res.json();
  if (data.matches && data.matches.length) {
    const m = data.matches[0];
    labelEl.textContent = `${m.id} (${m.score.toFixed(2)})`;
    if (m.score >= threshold) {
      mergeBtn.classList.remove('d-none');
      newBtn.classList.remove('d-none');
    } else {
      mergeBtn.classList.add('d-none');
      newBtn.classList.add('d-none');
    }
  } else {
    labelEl.textContent = 'No match';
    mergeBtn.classList.add('d-none');
    newBtn.classList.add('d-none');
  }
}

mergeBtn?.addEventListener('click', () => {
  mergeBtn.classList.add('d-none');
  newBtn.classList.add('d-none');
  // Placeholder for merge action; actual call handled server-side
});

newBtn?.addEventListener('click', () => {
  mergeBtn.classList.add('d-none');
  newBtn.classList.add('d-none');
});

startCamera();
setInterval(searchFrame, 1000);
