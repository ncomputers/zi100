// Purpose: Live search via webcam for Face DB search card

export function initFaceDbSearchLive() {
  const video = document.getElementById('searchVideo');
  const overlay = document.getElementById('searchOverlay');
  const thresholdInput = document.getElementById('threshold');
  const results = document.getElementById('results');
  if (!(video && overlay)) return { stop() {} };

  let stream = null;
  let timer = null;
  const capture = document.createElement('canvas');
  const ctx = capture.getContext('2d');
  const octx = overlay.getContext('2d');
  const FRAME_INTERVAL = 500; // ~2 FPS
  const INACTIVITY_TIMEOUT = 10_000; // ms
  let lastActive = Date.now();

  async function start() {
    try {
      if (!navigator.mediaDevices?.getUserMedia) throw new Error('unsupported');
      stream = await navigator.mediaDevices.getUserMedia({ video: true });
      video.srcObject = stream;
      video.onloadedmetadata = () => {
        const maxW = 320;
        const scale = Math.min(1, maxW / video.videoWidth);
        const w = Math.round(video.videoWidth * scale);
        const h = Math.round(video.videoHeight * scale);
        [video.width, video.height] = [w, h];
        [overlay.width, overlay.height] = [w, h];
        [capture.width, capture.height] = [w, h];
        tick();
      };
    } catch (err) {
      console.error('Camera start failed', err);
    }
  }

  async function tick() {
    if (!stream) return;
    ctx.drawImage(video, 0, 0, capture.width, capture.height);
    const b64 = capture.toDataURL('image/jpeg', 0.7).split(',')[1];
    const payload = {
      image: b64,
      threshold: parseFloat(thresholdInput.value || '0')
    };
    try {
      const resp = await fetch('/process_frame', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      });
      const data = await resp.json();
      octx.clearRect(0, 0, overlay.width, overlay.height);
      if (results) results.innerHTML = '';
      if (Array.isArray(data.faces)) {
        if (data.faces.length) lastActive = Date.now();
        data.faces.forEach(f => {
          const [x, y, w, h] = f.box;
          octx.strokeStyle = 'lime';
          octx.lineWidth = 2;
          octx.strokeRect(x, y, w, h);
          octx.fillStyle = 'lime';
          octx.font = '14px sans-serif';
          const label = `${f.name || 'unknown'} ${f.id || ''} ${f.confidence ? f.confidence.toFixed(2) : ''}`.trim();
          octx.fillText(label, x, y - 4);
          if (results) {
            results.insertAdjacentHTML('beforeend', `
              <div class="col-md-3 text-center mb-3">
                <div class="card shadow-sm p-2">
                  <div>${f.name || ''}</div>
                  <div class="text-muted">${f.id || ''} ${f.confidence ? f.confidence.toFixed(2) : ''}</div>
                </div>
              </div>
            `);
          }
        });
      }
    } catch (err) {
      console.error('process_frame failed', err);
    }
    if (Date.now() - lastActive > INACTIVITY_TIMEOUT) {
      stop();
      return;
    }
    timer = setTimeout(tick, FRAME_INTERVAL);
  }

  function stop() {
    if (timer) clearTimeout(timer);
    if (stream) {
      stream.getTracks().forEach(t => t.stop());
      stream = null;
    }
  }

  window.addEventListener('beforeunload', stop);
  start();
  return { stop };
}
