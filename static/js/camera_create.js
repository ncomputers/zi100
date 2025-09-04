// Purpose: handle camera create form and preview

document.addEventListener("DOMContentLoaded", () => {
  const nameEl = document.getElementById("name");
  const urlEl = document.getElementById("url");
  const typeEl = document.getElementById("type");
  const profileEl = document.getElementById("profile");
  const orientationEl = document.getElementById("orientation");
  const resolutionEl = document.getElementById("resolution");
  const transportEl = document.getElementById("transport");
  const ppeEl = document.getElementById("ppe");
  const vmsEl = document.getElementById("vms");
  const faceRecogEl = document.getElementById("face_recog");
  const inoutCountEl = document.getElementById("inout_count");
  const reverseEl = document.getElementById("reverse");
  const showEl = document.getElementById("show");

  const testBtn = document.getElementById("testPreview");
  const saveBtn = document.getElementById("saveBtn");
  const saveActivateBtn = document.getElementById("saveActivateBtn");

  const urlHint = document.getElementById("urlHint");
  const previewImg = document.getElementById("previewImg");
  const previewLog = document.getElementById("previewLog");
  const previewModalEl = document.getElementById("previewModal");
  const modal = new bootstrap.Modal(previewModalEl);

  let previewUrl = null;

  const allowedSchemes = ["rtsp:", "http:", "https:", "rtmp:", "srt:"];

  function mask(text) {
    return text.replace(/(?<=:\/\/)([^:@\s]+):([^@\/\s]+)@/g, "***:***@");
  }

  function validateUrl() {
    const url = urlEl.value.trim();
    let msg = "";
    if (!url) {
      msg = "URL required";
    } else {
      try {
        const u = new URL(url);
        if (!allowedSchemes.includes(u.protocol)) {
          msg = "Unsupported scheme";
        }
      } catch {
        msg = "Invalid URL";
      }
    }
    if (!msg && url.endsWith(".m3u8")) {
      msg = "HLS fallback note: preview may be delayed";
      urlHint.className = "text-warning";
    } else {
      urlHint.className = msg ? "text-danger" : "form-text";
    }
    urlHint.textContent = msg;
    return !msg;
  }

  urlEl.addEventListener("input", validateUrl);
  validateUrl();

  function clearErrors() {
    document
      .querySelectorAll(".is-invalid")
      .forEach((el) => el.classList.remove("is-invalid"));
    document
      .querySelectorAll(".invalid-feedback")
      .forEach((el) => (el.textContent = ""));
  }

  function applyErrors(errors) {
    errors.forEach((err) => {
      const field = err.loc[err.loc.length - 1];
      const el = document.getElementById(field);
      if (el) {
        el.classList.add("is-invalid");
        const fb = el.parentElement.querySelector(".invalid-feedback");
        if (fb) fb.textContent = err.msg;
      }
    });
  }

  function buildPayload(activate = false) {
    return {
      name: nameEl.value.trim(),
      url: urlEl.value.trim(),
      type: typeEl.value,
      profile: profileEl.value,
      orientation: orientationEl.value,
      resolution: resolutionEl.value,
      transport: transportEl.value || undefined,
      show: showEl.checked,
      ppe: ppeEl.checked,
      vms: vmsEl.checked,
      face_recog: faceRecogEl.checked,
      inout_count: inoutCountEl.checked,
      reverse: reverseEl.checked,
      activate,
    };
  }

  async function startPreview() {
    if (!validateUrl()) return;
    testBtn.disabled = true;
    previewLog.textContent = "";
    clearErrors();
    try {
      const body = buildPayload();
      const r = await fetch("/api/cameras/test", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      if (r.status === 422) {
        const data = await r.json();
        applyErrors(data.detail || []);
        return;
      }
      const data = await r.json();
      previewUrl = data.notes;
      previewImg.src = `${previewUrl}&fps=10`;

      if (data.log) {
        const logText = Array.isArray(data.log)
          ? data.log.join("\n")
          : data.log;
        previewLog.textContent = mask(logText);
      }
      modal.show();
    } catch (err) {
      urlHint.textContent = "Preview failed";
      urlHint.className = "text-danger";
    } finally {
      testBtn.disabled = false;
    }
  }

  function stopPreview() {
    if (!previewUrl) return;
    previewImg.removeAttribute("src");
    previewLog.textContent = "";
    previewUrl = null;
  }

  previewModalEl.addEventListener("hidden.bs.modal", stopPreview);

  testBtn.addEventListener("click", startPreview);

  async function save(activate = false) {
    if (!validateUrl()) return;
    clearErrors();
    const body = buildPayload();
    const r = await fetch("/api/cameras", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    if (r.status === 422) {
      const data = await r.json();
      applyErrors(data.detail || []);
      return;
    }
    if (!r.ok) {
      const err = await r.json().catch(() => ({}));
      const msg = err.message || "Save failed";
      if (typeof showToast === "function") showToast(msg, "danger");
      else alert(msg);
      return;
    }
    const data = await r.json();
    if (activate) {
      try {
        const a = await fetch(`/cameras/${data.id}/enabled`, {
          method: "PATCH",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ enabled: true }),
        });
        if (!a.ok) {
          const err = await a.json().catch(() => ({}));
          const msg = err.message || "Activation failed";
          if (typeof showToast === "function") showToast(msg, "danger");
          else alert(msg);
        }
      } catch (_) {
        if (typeof showToast === "function")
          showToast("Activation failed", "danger");
      }
    }
    window.location.href = "/cameras";
  }

  saveBtn.addEventListener("click", () => save(false));
  saveActivateBtn.addEventListener("click", () => save(true));
});
