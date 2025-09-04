/**
 * PhotoUploader component
 * Handles webcam, CCTV stream selection, file uploads and cropping via CropperJS.
 * Emits a base64 string of the cropped image through a callback.
 */
const faceModelsPromise = (async () => {
  if (typeof faceapi === "undefined") {
    console.warn("face-api.js not available; face detection disabled");
    return false;
  }
  try {
    // load weights from remote repository
    await faceapi.nets.tinyFaceDetector.loadFromUri(
      "https://raw.githubusercontent.com/ncomputers/faceModal_1/main",
    );
    return true;
  } catch (err) {
    console.warn("face-api models failed to load", err);
    return false;
  }
})();

export class PhotoUploader {
  constructor(opts) {
    this.video = opts.videoEl;
    this.preview = opts.previewEl || null;
    this.startBtn = opts.startBtn || null;
    this.stopBtn = opts.stopBtn || null;
    this.captureBtn = opts.captureBtn;
    this.uploadBtn = opts.uploadBtn || null;
    this.camsSelect = opts.camsSelect || null;
    this.cctvSelect = opts.cctvSelect || null;
    this.uploadInput = opts.uploadInput;
    this.resetBtn = opts.resetBtn || null;
    this.changeBtn = opts.changeBtn || null;
    this.onCapture =
      typeof opts.onCapture === "function" ? opts.onCapture : null;
    if (!this.onCapture) {
      console.warn("PhotoUploader instantiated without onCapture callback");
    }
    this.onPreview = opts.onPreview || null;
    this.brightnessInput = opts.brightnessInput || null;
    this.aspectRatio =
      typeof opts.aspectRatio === "number" ? opts.aspectRatio : 1;
    this.container =
      opts.container || this.video?.closest(".photo-controls") || null;
    this.hiddenInput =
      opts.hiddenInput ||
      this.container?.querySelector('input[type="hidden"]') ||
      null;
    this.photoBox =
      this.video?.parentElement || this.preview?.parentElement || null;
    const prefix = this.container?.dataset.prefix
      ? this.container.dataset.prefix + "_"
      : "";
    this.noPhotoCheckbox =
      opts.noPhotoCheckbox ||
      document.getElementById(`${prefix}noPhoto`) ||
      null;
    this.errorBox =
      opts.errorBox ||
      (this.container
        ? this.container.querySelector('[id$="cameraError"]')
        : null);
    this.maxSize = typeof opts.maxSize === "number" ? opts.maxSize : 500 * 1024;
    this.wasRequired = this.hiddenInput?.hasAttribute("required");
    this.stream = null;
    this.cropper = null;
    this.cropModal = null; // Bootstrap modal element
    this.modalInstance = null; // bootstrap.Modal instance
    this.cropImg = null;
    this.modelsLoaded = false;
    this.faceThreshold =
      typeof opts.faceThreshold === "number" ? opts.faceThreshold : 0.4;
    this.objectUrl = null; // tracks current object URL for revocation
    this.previewCanvas = null; // live preview during cropping
    this.lastFaceBox = null; // detected face box for auto-fit
    this.camsLoaded = false;
    this.source = "none";
  }

  async init() {
    try {
      this.modelsLoaded = await faceModelsPromise;
    } catch (err) {
      console.warn("face detection models not loaded", err);
      this.modelsLoaded = false;
    }
    if (!this.modelsLoaded) {
      this.showError("Face detection unavailable; manual crop only.");
    }
    if (this.photoBox) {
      this.photoBox.style.width = "200px";
      this.photoBox.style.height = this.aspectRatio === 1 ? "200px" : "266px";
    }
    if (this.startBtn) {
      this.captureBtn?.setAttribute("disabled", "disabled");
      this.startBtn.addEventListener("click", async () => {
        try {
          await this.startCam();
          this.captureBtn?.removeAttribute("disabled");
          this.startBtn.classList.add("d-none");
          this.stopBtn?.classList.remove("d-none");
        } catch (err) {
          this.showError("Unable to access camera.");
        }
      });
    }
    this.stopBtn?.addEventListener("click", () => {
      this.stopStream();
      this.startBtn?.classList.remove("d-none");
      this.stopBtn?.classList.add("d-none");
      this.captureBtn?.setAttribute("disabled", "disabled");
    });
    this.captureBtn?.addEventListener("click", async () => {
      try {
        if (!this.startBtn) await this.startCam();
        await this.capture();
      } catch (err) {
        this.showError("Capture failed");
        console.error("capture failed", err);
      }
    });
    this.uploadBtn?.addEventListener("click", () => {
      this.clearError();
      this.uploadInput?.click();
    });
    this.uploadInput?.addEventListener("change", (e) => this.handleUpload(e));
    this.resetBtn?.addEventListener("click", () => this.reset());
    this.changeBtn?.addEventListener("click", () => this.uploadInput?.click());
    this.brightnessInput?.addEventListener("input", () =>
      this.updateBrightness(),
    );
    this.noPhotoCheckbox?.addEventListener("change", () => {
      if (this.noPhotoCheckbox.checked) {
        this.reset();
        this.container?.classList.add("d-none");
        this.hiddenInput?.removeAttribute("required");
        if (this.hiddenInput) this.hiddenInput.value = "";
      } else {
        this.container?.classList.remove("d-none");
        if (this.wasRequired)
          this.hiddenInput?.setAttribute("required", "required");
      }
    });
    if (this.noPhotoCheckbox?.checked) {
      this.noPhotoCheckbox.dispatchEvent(new Event("change"));
    }

    const parentModal = this.container?.closest(".modal");
    parentModal?.addEventListener("hidden.bs.modal", () => this.stopStream());
    window.addEventListener("pagehide", () => this.stopStream());
    document.addEventListener("visibilitychange", () => {
      if (document.hidden) this.stopStream();
    });
  }

  async loadCams() {
    if (this.camsSelect) {
      try {
        // Populate local webcam list
        const devices = await navigator.mediaDevices.enumerateDevices();
        const cams = devices.filter((d) => d.kind === "videoinput");
        this.camsSelect.innerHTML = "";
        cams.forEach((c, idx) => {
          const o = document.createElement("option");
          o.value = c.deviceId;
          o.textContent = c.label || `Camera ${idx + 1}`;
          this.camsSelect.appendChild(o);
        });
      } catch (err) {
        this.showError(
          "Camera access denied or not supported. Please upload an image instead.",
        );
      }
    }

    if (!this.cctvSelect) return; // Skip CCTV fetch when not provided

    try {
      const resp = await fetch("/invite/cctv");
      if (!resp.ok) return;
      const list = await resp.json();
      list.forEach((c) => {
        const o = document.createElement("option");
        o.value = c.id;
        o.textContent = c.name;
        this.cctvSelect.appendChild(o);
      });
    } catch (err) {
      console.error("CCTV list failed", err);
    }
    this.camsLoaded = true;
  }

  async startCam() {
    if (!this.camsLoaded) {
      try {
        await this.loadCams();
      } catch (err) {
        /* ignore */
      }
    }
    const cctvId = this.cctvSelect?.value;
    if (cctvId) {
      this.stopStream();
      this.video.srcObject = null;
      this.video.src = `/stream/${cctvId}`;
      await this.video.play();
      this.video.classList.remove("d-none");

      return;
    }
    const id = this.camsSelect?.value;
    this.stopStream();
    if (!navigator.mediaDevices?.getUserMedia) {
      this.showError(
        'Camera access is not supported. <a href="https://support.google.com/chrome/answer/2693767" target="_blank" rel="noopener">Check browser settings</a>',
      );
      throw new Error("getUserMedia unsupported");
    }
    try {
      this.setLoading(true);
      this.showError("Requesting camera access…");
      this.stream = await navigator.mediaDevices.getUserMedia({
        video: { deviceId: id ? { exact: id } : undefined },
      });
      this.video.srcObject = this.stream;
      await this.video.play();
      this.video.classList.remove("d-none");
      this.clearError();
      this.resetBrightness();
      this.brightnessInput?.classList.remove("d-none");
      this.brightnessInput?.parentElement?.classList.remove("d-none");
      this.updateBrightness();
    } catch (err) {
      if (err.name === "NotAllowedError") {
        this.showError(
          'Camera access was denied. Please enable permissions in your browser settings. <a href="https://support.google.com/chrome/answer/2693767" target="_blank" rel="noopener">Open settings</a>',
        );
      } else {
        this.showError("Unable to start camera. Check permissions.");
      }
      throw err;
    } finally {
      this.setLoading(false);
    }
  }

  stopStream() {
    if (this.stream) {
      this.stream.getTracks().forEach((t) => t.stop());
      this.stream = null;
    }
    this.brightnessInput?.classList.add("d-none");
    this.brightnessInput?.parentElement?.classList.add("d-none");
    this.resetBrightness();
  }

  setLoading(loading) {
    const controls = [
      this.startBtn,
      this.captureBtn,
      this.uploadBtn,
      this.camsSelect,
      this.cctvSelect,
      this.uploadInput,
    ];
    controls.forEach((el) => {
      if (!el) return;
      if (loading) el.setAttribute("disabled", "disabled");
      else el.removeAttribute("disabled");
    });
    if (loading) this.container?.classList.add("loading");
    else this.container?.classList.remove("loading");
  }

  async canvasToBlob(canvas) {
    if (canvas.toBlob) {
      return await new Promise((res) => canvas.toBlob(res, "image/jpeg", 0.8));
    }
    // Fallback for browsers without canvas.toBlob
    const dataUrl = canvas.toDataURL("image/jpeg", 0.8);
    const b64 = dataUrl.split(",")[1];
    const bin = atob(b64);
    const bytes = new Uint8Array(bin.length);
    for (let i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i);
    return new Blob([bytes], { type: "image/jpeg" });
  }

  async capture() {
    const canvas = document.createElement("canvas");
    canvas.width = this.video.videoWidth;
    canvas.height = this.video.videoHeight;
    const ctx = canvas.getContext("2d");
    if (ctx) {
      const b = this.brightnessInput ? this.brightnessInput.value : 1;
      ctx.filter = `brightness(${b})`;
      ctx.drawImage(this.video, 0, 0);
      ctx.filter = "none";
    }
    const processed = this.applyAdjustments(canvas);
    const blob = await this.canvasToBlob(processed);
    if (!blob) return;
    const url = URL.createObjectURL(blob);
    this.objectUrl = url;
    this.source = "camera";
    const opened = await this.processImage(url);
    if (!opened) {
      URL.revokeObjectURL(url);
      this.objectUrl = null;
      if (blob.size > this.maxSize) {
        this.showError("Image too large (max 500 KB)");
        return;
      }
      const data = await new Promise((res, rej) => {
        const reader = new FileReader();
        reader.onloadend = () => res(reader.result);
        reader.onerror = rej;
        reader.readAsDataURL(blob);
      });
      if (this.hiddenInput) this.hiddenInput.value = data;
      if (this.onCapture) this.onCapture(data, "camera");
      this.showPreview(data);
      this.clearError();
    }
    this.stopStream();
    this.stopBtn?.classList.add("d-none");
    this.startBtn?.classList.remove("d-none");
  }

  async handleUpload(e) {
    const file = e.target.files[0];
    if (!file) return;
    if (!file.type.startsWith("image/")) {
      this.showError("Please select a valid image file.");
      e.target.value = "";
      return;
    }
    const url = URL.createObjectURL(file);
    let cropperOpened = false;
    this.objectUrl = url;
    this.source = "upload";
    try {
      cropperOpened = await this.processImage(url);
      if (!cropperOpened) {
        const img = new Image();
        img.src = url;
        await new Promise((res) => (img.onload = res));
        const canvas = document.createElement("canvas");
        canvas.width = img.width;
        canvas.height = img.height;
        const ctx = canvas.getContext("2d");
        ctx.drawImage(img, 0, 0);
        const processed = this.applyAdjustments(canvas);
        const blob = await this.canvasToBlob(processed);
        URL.revokeObjectURL(url);
        this.objectUrl = null;
        if (!blob) return;
        if (blob.size > this.maxSize) {
          this.showError("Image too large (max 500 KB)");
          return;
        }
        await new Promise((res, rej) => {
          const reader = new FileReader();
          reader.onloadend = () => {
            const data = reader.result;
            if (this.hiddenInput) this.hiddenInput.value = data;
            if (this.onCapture) this.onCapture(data, "upload");
            this.showPreview(data);
            this.clearError();
            res();
          };
          reader.onerror = rej;
          reader.readAsDataURL(blob);
        });
      }
    } catch (err) {
      URL.revokeObjectURL(url);
      this.objectUrl = null;
      this.showError("Image processing failed");
      throw err;
    } finally {
      this.stopStream();
      e.target.value = "";
    }
  }

  async processImage(url) {
    // Detect a face if the models are available and use it to seed the cropper.
    // Regardless of detection success, the cropper modal is always opened so
    // users can fine‑tune or select their own crop before confirming.
    const faceBox = this.modelsLoaded ? await this.detectFace(url) : null;
    return this.openCropper(url, faceBox);
  }

  async detectFace(url) {
    try {
      const img = new Image();
      img.crossOrigin = "anonymous";
      img.src = url;
      await new Promise((res) => (img.onload = res));
      let det = await faceapi.detectSingleFace(
        img,
        new faceapi.TinyFaceDetectorOptions({
          scoreThreshold: this.faceThreshold,
        }),
      );
      if (!det) {
        det = await faceapi.detectSingleFace(
          img,
          new faceapi.TinyFaceDetectorOptions({
            scoreThreshold: Math.max(this.faceThreshold * 0.5, 0.1),
          }),
        );
      }
      if (det) {
        const box = det.box;
        let pad = 20;
        if (det.score < this.faceThreshold + 0.1) pad = 40;
        const sx = Math.max(box.x - pad, 0);
        const sy = Math.max(box.y - pad, 0);
        const sw = Math.min(box.width + pad * 2, img.width - sx);
        const sh = Math.min(box.height + pad * 2, img.height - sy);
        const size = Math.max(sw, sh);
        const cx = sx + sw / 2;
        const cy = sy + sh / 2;
        const x = Math.max(0, Math.min(cx - size / 2, img.width - size));
        const y = Math.max(0, Math.min(cy - size / 2, img.height - size));
        return { x, y, width: size, height: size };
      }
    } catch (err) {
      console.warn("face detection failed", err);
    }
    return null;
  }

  openCropper(url, box = null) {
    return new Promise((resolve) => {
      if (
        typeof Cropper === "undefined" ||
        typeof bootstrap === "undefined" ||
        !bootstrap.Modal
      ) {
        this.showError("Image cropper failed to load. Using original image.");
        resolve(false);
        return;
      }
      if (!this.cropModal) this.buildCropper();
      this.lastFaceBox = box;
      const autoBtn = this.cropModal.querySelector("#pcAuto");
      if (autoBtn) {
        if (box && this.modelsLoaded) autoBtn.classList.remove("d-none");
        else autoBtn.classList.add("d-none");
      }
      const cancelBtn = this.cropModal.querySelector("#pcCancel");
      const useBtn = this.cropModal.querySelector("#pcUse");
      if (!cancelBtn || !useBtn) {
        if (!cancelBtn)
          console.error("PhotoUploader: cancel button '#pcCancel' not found");
        if (!useBtn)
          console.error("PhotoUploader: use button '#pcUse' not found");
        resolve(false);
        return;
      }
      const onCancel = () => {
        cancelBtn.removeEventListener("click", onCancel);
        useBtn.removeEventListener("click", onUse);
        this.closeCropper();
        resolve(false);
      };
      const onUse = async () => {
        const ok = await this.useImage();
        if (ok) {
          cancelBtn.removeEventListener("click", onCancel);
          useBtn.removeEventListener("click", onUse);
          resolve(true);
        } else {
          resolve(false);
        }
      };
      cancelBtn.addEventListener("click", onCancel);
      useBtn.addEventListener("click", onUse);
      // Wait for image load before initializing cropper
      this.cropImg.onload = () => {
        this.cropImg.onload = null;
        if (this.cropper) {
          this.cropper.destroy();
        }
        this.cropper = new Cropper(this.cropImg, {
          viewMode: 1,
          aspectRatio: this.aspectRatio,
          ready: () => {
            if (box) {
              this.cropper.setData(box);
            }
            this.updateCropPreview();
          },
          crop: () => this.updateCropPreview(),
        });
      };
      this.cropImg.src = url;
      this.modalInstance.show();
    });
  }

  buildCropper() {
    this.cropModal = document.createElement("div");
    this.cropModal.className = "modal fade";
    this.cropModal.tabIndex = -1;
    const pWidth = 200;
    const pHeight = this.aspectRatio === 1 ? 200 : 266;
    this.cropModal.innerHTML = `
      <div class="modal-dialog modal-dialog-centered">
        <div class="modal-content">
          <div class="modal-body text-center">
            <div class="d-flex justify-content-center">
              <img id="pcImg" class="img-fluid" alt="crop">
              <canvas id="pcPreview" class="ms-2 border" width="${pWidth}" height="${pHeight}"></canvas>
            </div>
          </div>
          <div class="modal-footer">
            <button type="button" class="btn btn-sm btn-secondary me-2" id="pcCancel">Cancel</button>
            <button type="button" class="btn btn-sm btn-outline-secondary me-2" id="pcRotate">Rotate</button>
            <button type="button" class="btn btn-sm btn-outline-secondary me-2 d-none" id="pcAuto">Auto-fit face</button>
            <button type="button" class="btn btn-sm btn-primary" id="pcUse">Use Image</button>
          </div>
        </div>
      </div>`;
    document.body.appendChild(this.cropModal);
    // Initialize Bootstrap modal without a backdrop so the page isn't obscured
    this.modalInstance = new bootstrap.Modal(this.cropModal, {
      backdrop: false,
    });
    this.cropImg = this.cropModal.querySelector("#pcImg");
    this.previewCanvas = this.cropModal.querySelector("#pcPreview");
    this.cropModal
      .querySelector("#pcRotate")
      .addEventListener("click", () => this.cropper?.rotate(90));
    this.cropModal.querySelector("#pcAuto").addEventListener("click", () => {
      if (this.lastFaceBox && this.cropper)
        this.cropper.setData(this.lastFaceBox);
    });
  }

  closeCropper() {
    if (this.cropper) {
      this.cropper.destroy();
      this.cropper = null;
    }
    if (this.modalInstance) {
      this.modalInstance.hide();
    }
    if (this.cropImg) {
      this.cropImg.src = "";
    }
    if (this.objectUrl) {
      URL.revokeObjectURL(this.objectUrl);
      this.objectUrl = null;
    }
    if (this.previewCanvas) {
      const ctx = this.previewCanvas.getContext("2d");
      ctx.clearRect(0, 0, this.previewCanvas.width, this.previewCanvas.height);
    }
  }

  async useImage() {
    if (!this.cropper) return false;
    const canvas = this.cropper.getCroppedCanvas();
    const processed = this.applyAdjustments(canvas);
    const blob = await this.canvasToBlob(processed);
    if (!blob) return false;
    if (!["image/jpeg", "image/png"].includes(blob.type)) {
      this.showError("Invalid image type");
      return false;
    }
    if (blob.size > this.maxSize) {
      this.showError("Image too large (max 500 KB)");
      return false;
    }
    await new Promise((res, rej) => {
      const reader = new FileReader();
      reader.onloadend = () => {
        const data = reader.result;
        if (this.hiddenInput) this.hiddenInput.value = data;
        if (this.onCapture) this.onCapture(data, this.source);
        this.showPreview(data);
        this.closeCropper();
        this.clearError();
        res();
      };
      reader.onerror = rej;
      reader.readAsDataURL(blob);
    });
    return true;
  }

  applyLevelsGamma(canvas, gamma = 0.9) {
    const ctx = canvas.getContext("2d");
    if (!ctx) return;
    const { width, height } = canvas;
    const img = ctx.getImageData(0, 0, width, height);
    const data = img.data;
    let min = 255;
    let max = 0;
    for (let i = 0; i < data.length; i += 4) {
      const lum =
        0.2126 * data[i] + 0.7152 * data[i + 1] + 0.0722 * data[i + 2];
      if (lum < min) min = lum;
      if (lum > max) max = lum;
    }
    const range = max - min || 1;
    const invGamma = 1 / gamma;
    for (let i = 0; i < data.length; i += 4) {
      const lum =
        0.2126 * data[i] + 0.7152 * data[i + 1] + 0.0722 * data[i + 2];
      const norm = (lum - min) / range;
      const adj = Math.pow(norm, invGamma) * 255;
      const ratio = lum ? adj / lum : 0;
      data[i] = Math.min(255, data[i] * ratio);
      data[i + 1] = Math.min(255, data[i + 1] * ratio);
      data[i + 2] = Math.min(255, data[i + 2] * ratio);
    }
    ctx.putImageData(img, 0, 0);
  }

  clampCanvas(canvas, max = 1024) {
    const { width, height } = canvas;
    const scale = Math.min(1, max / Math.max(width, height));
    if (scale < 1) {
      const c = document.createElement("canvas");
      c.width = Math.round(width * scale);
      c.height = Math.round(height * scale);
      const ctx = c.getContext("2d");
      ctx.drawImage(canvas, 0, 0, c.width, c.height);
      return c;
    }
    return canvas;
  }

  applyAdjustments(canvas) {
    this.applyLevelsGamma(canvas);
    return this.clampCanvas(canvas, 1024);
  }

  updateCropPreview() {
    if (!this.cropper || !this.previewCanvas) return;
    const canvas = this.cropper.getCroppedCanvas({
      width: this.previewCanvas.width,
      height: this.previewCanvas.height,
    });
    this.applyLevelsGamma(canvas);
    const ctx = this.previewCanvas.getContext("2d");
    ctx.clearRect(0, 0, this.previewCanvas.width, this.previewCanvas.height);
    ctx.drawImage(
      canvas,
      0,
      0,
      this.previewCanvas.width,
      this.previewCanvas.height,
    );
  }

  showPreview(url) {
    this.onPreview?.(url);
    const img = this.preview;
    if (img) {
      img.src = url;
      img.classList.remove("d-none");
    }
    this.photoBox?.classList.remove("photo-placeholder");
    if (this.video) {
      this.video.classList.add("d-none");
    }
    this.captureBtn?.classList.add("d-none");
    this.uploadBtn?.classList.add("d-none");
    this.startBtn?.classList.add("d-none");
    this.stopBtn?.classList.add("d-none");
    this.brightnessInput?.classList.add("d-none");
    this.brightnessInput?.parentElement?.classList.add("d-none");
    const actionBox = this.resetBtn?.parentElement;
    this.resetBtn?.classList.remove("d-none");
    this.changeBtn?.classList.remove("d-none");
    actionBox?.classList.remove("d-none");
  }

  showVideo() {
    const img = this.preview;
    if (img) {
      img.classList.add("d-none");
      img.src = "";
    }
    if (this.video) {
      this.video.classList.add("d-none");
    }
    this.photoBox?.classList.add("photo-placeholder");
    this.captureBtn?.classList.remove("d-none");
    this.uploadBtn?.classList.remove("d-none");
    this.startBtn?.classList.remove("d-none");
    this.stopBtn?.classList.add("d-none");
    const actionBox = this.resetBtn?.parentElement;
    this.resetBtn?.classList.add("d-none");
    this.changeBtn?.classList.add("d-none");
    actionBox?.classList.add("d-none");
    this.brightnessInput?.classList.add("d-none");
    this.brightnessInput?.parentElement?.classList.add("d-none");
    this.resetBrightness();
  }

  reset() {
    this.stopStream();
    this.showVideo();
    if (this.uploadInput) this.uploadInput.value = "";
    this.source = "none";
    if (this.onCapture) this.onCapture("", "none");
    if (this.hiddenInput) this.hiddenInput.value = "";
    this.clearError();
    if (!this.startBtn) {
      try {
        this.startCam();
      } catch (err) {
        /* ignore */
      }
    }
  }

  showError(msg) {
    if (this.errorBox) this.errorBox.innerHTML = msg;
    if (typeof window !== "undefined" && typeof window.alert === "function") {
      window.alert(msg);
    }
  }

  clearError() {
    if (this.errorBox) this.errorBox.innerHTML = "";
  }

  resetBrightness() {
    if (this.brightnessInput) {
      const def = this.brightnessInput.dataset.default || "1";
      this.brightnessInput.value = def;
    }
    if (this.video) this.video.style.filter = "";
  }

  updateBrightness() {
    if (this.brightnessInput && this.video) {
      const val = this.brightnessInput.value || 1;
      this.video.style.filter = `brightness(${val})`;
    }
  }
}

/**
 * Helper to create and initialise a PhotoUploader instance.
 *
 * Returns an object containing the {@link PhotoUploader} instance and a
 * `ready` promise that resolves once cameras and face models are loaded.
 * The uploader exposes methods such as:
 *  - startCam(): begin streaming from the selected camera
 *  - stopStream(): stop any active media stream
 *  - capture(): capture a frame from the current stream
 *  - handleUpload(e): process an uploaded file
 *  - openCropper(url): open the CropperJS modal
 *  - closeCropper(): destroy the cropper and hide the modal
 *  - useImage(): accept the cropped image and invoke onCapture
 *  - reset(): clear the preview and stop streaming
 *
 * @param {Object} opts Options for the uploader
 * @returns {{uploader: PhotoUploader, ready: Promise<void>}} uploader and init promise
 */
export function initPhotoUploader(opts) {
  const uploader = new PhotoUploader(opts);
  const ready = uploader.init();
  return { uploader, ready };
}

// Expose globally
if (typeof window !== "undefined") {
  window.PhotoUploader = PhotoUploader;
  window.initPhotoUploader = initPhotoUploader;
}
