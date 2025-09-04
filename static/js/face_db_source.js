// Purpose: Unified camera source handler for Face DB page
let stream = null;
let timer = null;
let controller = null;

function drawFaces(overlayCtx, data, infoDiv) {
  overlayCtx.clearRect(0, 0, overlayCtx.canvas.width, overlayCtx.canvas.height);
  if (!Array.isArray(data.faces)) {
    if (infoDiv) infoDiv.textContent = "";
    return;
  }
  data.faces.forEach((f) => {
    const [x, y, w, h] = f.box;
    overlayCtx.strokeStyle = "red";
    overlayCtx.lineWidth = 2;
    overlayCtx.strokeRect(x, y, w, h);
    overlayCtx.fillStyle = "red";
    overlayCtx.font = "14px sans-serif";
    const base = f.gate_pass_id || f.name || "unknown";
    const label =
      `${base} ${f.confidence ? f.confidence.toFixed(2) : ""}`.trim();
    overlayCtx.fillText(label, x, y - 4);
  });
  if (infoDiv && data.faces.length) {
    const f = data.faces[0];
    const lines = [
      `Name: ${f.name || ""}`,
      `Gate Pass ID: ${f.gate_pass_id || ""}`,
      `Visitor Type: ${f.visitor_type || ""}`,
      f.id ? `ID: ${f.id}` : "",
    ].filter(Boolean);
    infoDiv.textContent = lines.join("\n");
  } else if (infoDiv) {
    infoDiv.textContent = "";
  }
}

async function startBrowser(video, canvas, overlay, capture, infoDiv, params) {
  try {
    clearError();
    if (!navigator.mediaDevices?.getUserMedia) throw new Error("unsupported");
    stream = await navigator.mediaDevices.getUserMedia({ video: true });
    video.srcObject = stream;
    video.classList.remove("d-none");
    overlay.classList.remove("d-none");
    infoDiv.classList.remove("d-none");
    canvas.classList.add("d-none");
    video.onloadedmetadata = () => {
      overlay.width = video.videoWidth;
      overlay.height = video.videoHeight;
      overlay.style.width = `${video.videoWidth}px`;
      overlay.style.height = `${video.videoHeight}px`;
      overlay.style.zIndex = "1";
      capture.width = 320;
      capture.height = Math.floor(video.videoHeight * (320 / video.videoWidth));
      tickBrowser(video, capture, overlay, infoDiv, params);
    };
  } catch (err) {
    console.error("Camera start failed", err);
    let msg = "Unable to access camera.";
    if (err.name === "NotAllowedError") msg = "Camera access was denied.";
    else if (err.name === "NotFoundError") msg = "No camera device found.";
    else if (err.message === "unsupported")
      msg = "Camera not supported in this browser.";
    showError(msg);
  }
}

async function tickBrowser(video, capture, overlay, infoDiv, params) {
  if (!stream) return;
  const ctx = capture.getContext("2d");
  const octx = overlay.getContext("2d");
  ctx.drawImage(video, 0, 0, capture.width, capture.height);
  const b64 = capture.toDataURL("image/jpeg", 0.7).split(",")[1];
  const payload = {
    image: b64,
    scaleFactor: params.scaleFactor(),
    minNeighbors: params.minNeighbors(),
    threshold: params.threshold(),
    minFaceSize: params.minFaceSize(),
  };
  try {
    controller = new AbortController();
    const resp = await fetch("/process_frame", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
      signal: controller.signal,
    });
    const data = await resp.json();
    drawFaces(octx, data, infoDiv);
  } catch (err) {
    if (err.name !== "AbortError") {
      console.error("process_frame failed", err);
    }
    return;
  } finally {
    controller = null;
  }
  timer = setTimeout(
    () => tickBrowser(video, capture, overlay, infoDiv, params),
    500,
  );
}

async function startCamera(canvas, overlay, infoDiv, params, camId) {
  const ctx = canvas.getContext("2d");
  const octx = overlay.getContext("2d");
  canvas.classList.remove("d-none");
  overlay.classList.remove("d-none");
  infoDiv.classList.remove("d-none");
  overlay.style.zIndex = "1";
  videoHide();
  clearError();
  async function tick() {
    const url = `/process_camera/${camId}?scaleFactor=${params.scaleFactor()}&minNeighbors=${params.minNeighbors()}&threshold=${params.threshold()}&minFaceSize=${params.minFaceSize()}`;
    try {
      controller = new AbortController();
      const resp = await fetch(url, { signal: controller.signal });
      if (!resp.ok) throw new Error("request failed");
      const data = await resp.json();
      const img = new Image();
      img.onload = () => {
        if (canvas.classList.contains("d-none")) return;
        canvas.width = img.width;
        canvas.height = img.height;
        overlay.width = img.width;
        overlay.height = img.height;
        overlay.style.width = `${img.width}px`;
        overlay.style.height = `${img.height}px`;
        ctx.drawImage(img, 0, 0);
        drawFaces(octx, data, infoDiv);
      };
      img.src = `data:image/jpeg;base64,${data.image}`;
    } catch (err) {
      console.error("process_camera failed", err);
      showError("Unable to load camera stream.");

      return;
    } finally {
      controller = null;
    }
    timer = setTimeout(tick, 1000);
  }
  tick();
}

function videoHide() {
  const video = document.getElementById("liveVideo");
  if (video) video.classList.add("d-none");
}

let select, video, canvas, overlay, capture, infoDiv;
let scaleInput, neighborsInput, thresholdInput, sizeInput;
let scaleVal, neighborVal, thresholdVal, sizeVal;
let params;
let startBtn,
  cameraError,
  permState = "prompt";

function showError(msg) {
  if (cameraError) {
    cameraError.textContent = msg;
    cameraError.classList.remove("d-none");
  }
}

function clearError() {
  if (cameraError) {
    cameraError.textContent = "";
    cameraError.classList.add("d-none");
  }
}

function updateStartState() {
  const needPerm = select?.value === "browser";
  if (startBtn) startBtn.disabled = false;
  [scaleInput, neighborsInput, thresholdInput, sizeInput].forEach(
    (i) => i && (i.disabled = false),
  );
  if (needPerm && permState === "denied") {
    showError(
      "Camera access has been denied. Re-enable it in your browser settings.",
    );
  } else {
    clearError();
  }
}

async function checkPermissions() {
  if (!navigator.permissions?.query) {
    permState = "granted";
    updateStartState();
    return;
  }
  try {
    const result = await navigator.permissions.query({ name: "camera" });
    permState = result.state;
    updateStartState();
    result.onchange = () => {
      permState = result.state;
      updateStartState();
    };
  } catch (err) {
    console.warn("Permission query failed", err);
    permState = "prompt";
    updateStartState();
  }
}

export function initSource() {
  select = document.getElementById("sourceSelect");
  video = document.getElementById("liveVideo");
  canvas = document.getElementById("cameraCanvas");
  overlay = document.getElementById("overlayCanvas");
  capture = document.getElementById("captureCanvas");
  infoDiv = document.getElementById("liveFaceInfo");
  scaleInput = document.getElementById("scaleFactor");
  neighborsInput = document.getElementById("minNeighbors");
  thresholdInput = document.getElementById("recThreshold");
  sizeInput = document.getElementById("minFaceSize");
  scaleVal = document.getElementById("scaleVal");
  neighborVal = document.getElementById("neighborVal");
  thresholdVal = document.getElementById("recThreshVal");
  sizeVal = document.getElementById("minFaceVal");
  startBtn = document.getElementById("startCameraBtn");
  cameraError = document.getElementById("cameraError");
  if (!cameraError && startBtn?.parentNode) {
    cameraError = document.createElement("div");
    cameraError.id = "cameraError";
    cameraError.className = "text-danger mb-2 d-none";
    startBtn.parentNode.insertBefore(cameraError, startBtn);
  }

  const defaults = window.FACE_PARAM_DEFAULTS || {
    scaleFactor: 1.1,
    minNeighbors: 5,
    threshold: 0.6,
    minFaceSize: 60,
  };
  const policy = window.FACE_PARAM_POLICY || {};

  const clamp = (v, k) => {
    const lim = policy[k];
    if (!lim) return v;
    if (lim.min !== undefined) v = Math.max(v, lim.min);
    if (lim.max !== undefined) v = Math.min(v, lim.max);
    return v;
  };

  const loadPrefs = () => {
    let stored = {};
    try {
      stored = JSON.parse(localStorage.getItem("faceParams") || "{}");
    } catch {}
    scaleInput.value = clamp(
      stored.scaleFactor ?? defaults.scaleFactor,
      "scaleFactor",
    );
    neighborsInput.value = clamp(
      stored.minNeighbors ?? defaults.minNeighbors,
      "minNeighbors",
    );
    thresholdInput.value = clamp(
      stored.threshold ?? defaults.threshold,
      "threshold",
    );
    sizeInput.value = clamp(
      stored.minFaceSize ?? defaults.minFaceSize,
      "minFaceSize",
    );
  };

  params = {
    scaleFactor: () => parseFloat(scaleInput.value),
    minNeighbors: () => parseInt(neighborsInput.value, 10),
    threshold: () => parseFloat(thresholdInput.value),
    minFaceSize: () => parseInt(sizeInput.value, 10),
  };

  const updateLabels = () => {
    if (scaleVal) scaleVal.textContent = scaleInput.value;
    if (neighborVal) neighborVal.textContent = neighborsInput.value;
    if (thresholdVal) thresholdVal.textContent = thresholdInput.value;
    if (sizeVal) sizeVal.textContent = sizeInput.value;
  };
  const savePrefs = () => {
    localStorage.setItem(
      "faceParams",
      JSON.stringify({
        scaleFactor: params.scaleFactor(),
        minNeighbors: params.minNeighbors(),
        threshold: params.threshold(),
        minFaceSize: params.minFaceSize(),
      }),
    );
  };
  [scaleInput, neighborsInput, thresholdInput, sizeInput].forEach((el) =>
    el?.addEventListener("input", () => {
      updateLabels();
      savePrefs();
    }),
  );
  const resetBtn = document.getElementById("resetDefaultsBtn");
  resetBtn?.addEventListener("click", () => {
    scaleInput.value = defaults.scaleFactor;
    neighborsInput.value = defaults.minNeighbors;
    thresholdInput.value = defaults.threshold;
    sizeInput.value = defaults.minFaceSize;
    updateLabels();
    savePrefs();
  });
  loadPrefs();
  updateLabels();

  select.addEventListener("change", () => {
    updateStartState();
    start();
  });

  checkPermissions();
}

export async function start() {
  if (!select) return;
  stop();
  const src = select.value;
  if (src === "browser") {
    await startBrowser(video, canvas, overlay, capture, infoDiv, params);
  } else {
    await startCamera(canvas, overlay, infoDiv, params, src);
  }
}

export function stop() {
  if (controller) controller.abort();
  controller = null;
  if (timer) clearTimeout(timer);
  timer = null;
  if (stream) {
    stream.getTracks().forEach((t) => t.stop());
    stream = null;
  }
  if (canvas) canvas.classList.add("d-none");
  if (overlay) overlay.classList.add("d-none");
  if (infoDiv) {
    infoDiv.classList.add("d-none");
    infoDiv.textContent = "";
  }
  videoHide();
}
