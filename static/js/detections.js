// Demo client that overlays detection boxes on a video feed.
const video = document.getElementById('webcam');
const canvas = document.getElementById('overlay');
const ctx = canvas.getContext('2d');
let boxes = [];

function resize() {
  canvas.width = video.videoWidth;
  canvas.height = video.videoHeight;
}

video.addEventListener('loadedmetadata', resize);
window.addEventListener('resize', resize);

// Start webcam stream
navigator.mediaDevices.getUserMedia({ video: true }).then(stream => {
  video.srcObject = stream;
}).catch(err => console.error('Camera access denied', err));

// Connect to detections websocket
const ws = new WebSocket(`ws://${location.host}/ws/detections`);
ws.onmessage = ev => {
  const data = JSON.parse(ev.data);
  boxes = data.detections || [];
};

function draw() {
  ctx.clearRect(0, 0, canvas.width, canvas.height);
  boxes.forEach(b => {
    const x = b.x * canvas.width;
    const y = b.y * canvas.height;
    const w = b.width * canvas.width;
    const h = b.height * canvas.height;
    ctx.strokeStyle = 'red';
    ctx.lineWidth = 2;
    ctx.strokeRect(x, y, w, h);
  });
  requestAnimationFrame(draw);
}

requestAnimationFrame(draw);
