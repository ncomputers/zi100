// Purpose: client-side webcam face detection for Face DB page
let stream = null;
let intervalId = null;
let modelsLoaded = false;

const video = document.getElementById('video');
const canvas = document.getElementById('overlay');
const addBtn = document.getElementById('addFaceBtn');
const startBtn = document.getElementById('startBtn');
const stopBtn = document.getElementById('stopBtn');
const controls = document.getElementById('controls');
const statusEl = document.getElementById('status');

async function loadFaceApi() {
  if (window.faceapi) return;
  await new Promise((resolve, reject) => {
    const s = document.createElement('script');
    s.src = 'https://cdn.jsdelivr.net/npm/face-api.js@0.22.2/dist/face-api.min.js';
    s.onload = resolve;
    s.onerror = () => reject(new Error('Failed to load face-api.js'));
    document.head.appendChild(s);
  });
}

async function ensureModels() {
  if (modelsLoaded) return;
  const url = 'https://raw.githubusercontent.com/justadudewhohacks/face-api.js/master/weights';
  await faceapi.nets.tinyFaceDetector.loadFromUri(url);
  modelsLoaded = true;
}

async function start() {
  try {
    await loadFaceApi();
    await ensureModels();
  } catch (e) {
    statusEl.textContent = e.message;
    return;
  }
  try {
    stream = await navigator.mediaDevices.getUserMedia({ video: true });
  } catch (err) {
    statusEl.textContent = 'Camera access denied or unavailable.';
    return;
  }
  statusEl.textContent = '';
  video.srcObject = stream;
  await video.play();
  video.classList.remove('d-none');
  canvas.classList.remove('d-none');
  startBtn.disabled = true;
  stopBtn.disabled = false;
  const ctx = canvas.getContext('2d');
  const draw = async () => {
    const { videoWidth, videoHeight } = video;
    canvas.width = videoWidth;
    canvas.height = videoHeight;
    const detections = await faceapi.detectAllFaces(
      video,
      new faceapi.TinyFaceDetectorOptions()
    );
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    detections.forEach((d) => {
      const { x, y, width, height } = d.box;
      ctx.strokeStyle = 'red';
      ctx.lineWidth = 2;
      ctx.strokeRect(x, y, width, height);
      ctx.fillStyle = 'red';
      ctx.font = '16px sans-serif';
      ctx.fillText(`${(d.score * 100).toFixed(1)}%`, x, y > 10 ? y - 5 : 10);
    });
  };
  intervalId = setInterval(draw, 100);
}

function stop() {
  if (intervalId) clearInterval(intervalId);
  intervalId = null;
  if (stream) {
    stream.getTracks().forEach((t) => t.stop());
    stream = null;
  }
  const ctx = canvas.getContext('2d');
  ctx.clearRect(0, 0, canvas.width, canvas.height);
  startBtn.disabled = false;
  stopBtn.disabled = true;
}

addBtn.addEventListener('click', () => {
  addBtn.classList.add('d-none');
  controls.classList.remove('d-none');
  start();
});

startBtn.addEventListener('click', start);
stopBtn.addEventListener('click', stop);
