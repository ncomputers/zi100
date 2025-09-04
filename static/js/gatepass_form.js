import { initPhotoUploader } from "./photo_uploader.js";
import {
  validateEmail,
  showFieldError,
  clearFieldError,
} from "./validation.js";

// Initialize gate pass form
export async function initGatepassForm(cfg = {}) {
  // config from data attributes
  const form = document.getElementById("gateForm");
  const printBase =
    cfg.printBase || form.dataset.printBase || "/gatepass/print/";
  const defaultHost = cfg.defaultHost || form.dataset.defaultHost || "";

  // toast helper
  const toastEl = document.getElementById("toast");
  const toastMsg = document.getElementById("toastMsg");
  const showToast = (msg, variant = "primary", allowHtml = false) => {
    toastEl.className = `toast text-bg-${variant} border-0`;
    toastMsg.innerHTML = msg;

    bootstrap.Toast.getOrCreateInstance(toastEl).show();
  };

  // state
  const visitorData = {};
  const visitorSuggestions = {};
  const photoData = {};
  const hostData = {};
  const approvalData = {};

  // elements
  const inviteId = document.getElementById("inviteId");
  const vName = document.getElementById("vName");
  const vNameList = document.getElementById("vNameList");
  const vPhone = document.getElementById("vPhone");
  const vEmail = document.getElementById("vEmail");
  const vType = document.getElementById("vType");
  const vPurpose = document.getElementById("vPurpose");
  const vCompany = document.getElementById("vCompany");
  const vValid = document.getElementById("vValid");
  const pad = (n) => String(n).padStart(2, "0");
  const toLocalInputValue = (d) =>
    `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
  let validPicker;
  const refreshValidMin = () => {
    const now = new Date();
    vValid.min = toLocalInputValue(now);
    validPicker?.set("minDate", now);
  };
  refreshValidMin();
  const hName = document.getElementById("hName");
  const hDept = document.getElementById("hDept");
  const needApproval = document.getElementById("needApproval");
  const approverBox = document.getElementById("approverBox");
  const approverEmail = document.getElementById("approverEmail");
  const prevPhoto = document.getElementById("prevPhoto");
  const pName = document.getElementById("pName");
  const pPhone = document.getElementById("pPhone");
  const pEmail = document.getElementById("pEmail");
  const pType = document.getElementById("pType");
  const pCompany = document.getElementById("pCompany");
  const pHost = document.getElementById("pHost");
  const pPurpose = document.getElementById("pPurpose");
  const pGate = document.getElementById("pGate");
  const pValid = document.getElementById("pValid");
  const pStatus = document.getElementById("pStatus");
  const qrBox = document.getElementById("qrBox");
  const printBtn = document.getElementById("printBtn");
  const pdfBtn = document.getElementById("pdfBtn");
  const viewBtn = document.getElementById("viewBtn");
  const shareBtn = document.getElementById("shareBtn");
  const copyPassLinkBtn = document.getElementById("copyPassLinkBtn");
  const copyLinkBtn = document.getElementById("copyLinkBtn");
  const newBtn = document.getElementById("newBtn");
  const confirmBtn = document.getElementById("confirmBtn");
  const saveBtn = document.getElementById("saveBtn");
  const confirmModalEl = document.getElementById("confirmModal");
  const confirmModal = new bootstrap.Modal(confirmModalEl);
  const cmPhoto = confirmModalEl.querySelector("#prevPhoto");
  const cmName = confirmModalEl.querySelector("#pName");
  const cmPhone = confirmModalEl.querySelector("#pPhone");
  const cmEmail = confirmModalEl.querySelector("#pEmail");
  const cmType = confirmModalEl.querySelector("#pType");
  const cmCompany = confirmModalEl.querySelector("#pCompany");
  const cmHost = confirmModalEl.querySelector("#pHost");
  const cmPurpose = confirmModalEl.querySelector("#pPurpose");
  const cmValid = confirmModalEl.querySelector("#pValid");
  const controls = document.querySelector(".photo-controls");
  const prefix = controls?.dataset.prefix ? `${controls.dataset.prefix}_` : "";
  const getEl = (id) => document.getElementById(`${prefix}${id}`);
  const captureBtn = getEl("capturePhoto");
  const uploadBtn = getEl("uploadPhoto");
  const videoEl = getEl("preview");
  const photoPreviewEl = getEl("photoPreview");
  const uploadInput = getEl("upload");
  const capturedInput =
    getEl("captured") || document.getElementById("captured");
  const noPhotoChk = getEl("noPhoto") || document.getElementById("noPhoto");
  const toHostBtn = document.getElementById("toHost");
  const retakeBtn = getEl("retake");
  const changePhotoBtn = getEl("changePhoto");
  const brightnessInput = getEl("brightness");

  noPhotoChk?.addEventListener("change", () => {
    if (noPhotoChk.checked) {
      if (capturedInput) capturedInput.value = "";
      photoData.image = null;
      toHostBtn.disabled = false;
    } else {
      toHostBtn.disabled = !capturedInput?.value;
    }
  });

  retakeBtn?.addEventListener("click", () => {
    photoData.image = null;
    prevPhoto.src = "";
    updatePreview();
    toHostBtn.disabled = true;
  });

  // libraries init
  const iti = intlTelInput(vPhone, {
    initialCountry: "in",
    utilsScript:
      "https://cdn.jsdelivr.net/npm/intl-tel-input@19.5.5/build/js/utils.js",
  });
  let typeSelect;
  if (window.TomSelect) {
    try {
      typeSelect = new TomSelect("#vType");
      vType.classList.add("d-none");
    } catch (err) {
      console.error("TomSelect initialization failed", err);
    }
  }
  validPicker = flatpickr("#vValid", {
    enableTime: true,
    dateFormat: "Y-m-d\\TH:i",
    defaultDate: new Date(Date.now() + 3600 * 1000),
    minDate: new Date(),
    onChange: handleValidInput,
  });
  refreshValidMin();

  // live preview updates
  const storeVisitor = () => {
    visitorData.name = vName.value;
    visitorData.phone = iti.getNumber();
    visitorData.email = vEmail.value;
    visitorData.visitor_type = vType.value;
    visitorData.purpose = vPurpose.value;
    visitorData.company = vCompany.value;
    visitorData.valid_to = vValid.value;
  };
  const storeHost = () => {
    hostData.name = hName.value || defaultHost;
    hostData.department = hDept.value;
  };
  const storeApproval = () => {
    approvalData.needsApproval = needApproval.checked;
    approvalData.approverEmail = approverEmail.value;
  };
  const validateApproval = () => {
    if (needApproval.checked && !approverEmail.value.trim()) {
      showFieldError(approverEmail, "Approver email required");
      return false;
    }
    clearFieldError(approverEmail);
    return true;
  };
  const updatePreview = () => {
    pName.textContent = visitorData.name || "";
    pPhone.textContent = visitorData.phone || "";
    pEmail.textContent = visitorData.email || "—";
    pType.textContent = visitorData.visitor_type || "—";
    pCompany.textContent = visitorData.company || "—";
    pHost.textContent = hostData.name || "";
    pPurpose.textContent = visitorData.purpose || "";
    pValid.textContent = visitorData.valid_to || "—";
    if (cmPhoto) cmPhoto.src = photoData.image || prevPhoto.src;
    if (cmName) cmName.textContent = visitorData.name || "";
    if (cmPhone) cmPhone.textContent = visitorData.phone || "";
    if (cmEmail) cmEmail.textContent = visitorData.email || "—";
    if (cmType) cmType.textContent = visitorData.visitor_type || "—";
    if (cmCompany) cmCompany.textContent = visitorData.company || "—";
    if (cmHost) cmHost.textContent = hostData.name || "";
    if (cmPurpose) cmPurpose.textContent = visitorData.purpose || "";
    if (cmValid) cmValid.textContent = visitorData.valid_to || "—";
  };
  [vName, vPhone, vEmail, vPurpose, vCompany].forEach((el) =>
    el.addEventListener("input", () => {
      clearFieldError(el);
      storeVisitor();
      updatePreview();
    }),
  );
  function handleValidInput() {
    if (vValid.value && new Date(vValid.value) < new Date()) {
      showFieldError(vValid, "Date/time cannot be in the past");
      vValid.value = "";
    } else {
      clearFieldError(vValid);
    }
    storeVisitor();
    updatePreview();
  }
  vValid.addEventListener("input", handleValidInput);
  vType.addEventListener("change", () => {
    clearFieldError(vType);
    storeVisitor();
    updatePreview();
  });
  [hName, hDept].forEach((el) =>
    el.addEventListener("input", () => {
      clearFieldError(el);
      storeHost();
      updatePreview();
    }),
  );
  approverEmail.addEventListener("input", () => {
    clearFieldError(approverEmail);
    storeApproval();
  });

  storeVisitor();
  storeHost();
  storeApproval();
  updatePreview();

  inviteId.addEventListener("change", async () => {
    const id = inviteId.value.trim();
    if (!id) return;
    try {
      const r = await fetch(`/invite/${encodeURIComponent(id)}`);
      if (r.ok) {
        const d = await r.json();
        if (d.name) vName.value = d.name;
        if (d.phone) {
          iti.setNumber(d.phone);
          vPhone.value = d.phone;
        }
        if (d.email) vEmail.value = d.email;
        if (d.host) hName.value = d.host;
        if (d.purpose) vPurpose.value = d.purpose;
        if (d.expiry) vValid.value = d.expiry;
        storeVisitor();
        storeHost();
        updatePreview();
      }
    } catch (err) {
      console.error("invite fetch", err);
    }
  });

  const { uploader: photoHandler, ready: photoReady } = initPhotoUploader({
    videoEl,
    previewEl: photoPreviewEl,
    captureBtn,
    uploadBtn,
    resetBtn: retakeBtn,
    changeBtn: changePhotoBtn,
    uploadInput,
    hiddenInput: capturedInput,
    noPhotoCheckbox: noPhotoChk,
    brightnessInput,
    onCapture: (data) => {
      photoData.image = data;
      if (capturedInput) capturedInput.value = data;
      toHostBtn.disabled = false;
      updatePreview();
    },
  });
  // Wait for cameras and models to load before enabling controls
  await photoReady;

  function resetGatePass() {
    form.reset();
    pName.textContent =
      pPhone.textContent =
      pEmail.textContent =
      pType.textContent =
      pCompany.textContent =
      pHost.textContent =
      pPurpose.textContent =
        "";
    pGate.textContent = "Draft";
    pStatus.textContent = "Draft";
    pValid.textContent = "";
    qrBox.innerHTML = "";
    printBtn.disabled = true;
    pdfBtn.disabled = true;
    viewBtn.disabled = true;
    viewBtn.onclick = null;
    copyPassLinkBtn.classList.add("d-none");
    copyLinkBtn.classList.add("d-none");
    newBtn.classList.add("d-none");
    photoHandler.reset();
    photoHandler.closeCropper();
    photoHandler.stopStream();
    uploadInput.value = "";
    inviteId.value = "";
    if (typeSelect) {
      typeSelect.setValue("");
    }
    iti.setNumber("");
    refreshValidMin();
    validPicker.setDate(new Date(Date.now() + 3600 * 1000));
    clearFieldError(vValid);
    Object.keys(visitorData).forEach((k) => delete visitorData[k]);
    Object.keys(photoData).forEach((k) => delete photoData[k]);
    Object.keys(hostData).forEach((k) => delete hostData[k]);
    hName.value = defaultHost;
    hDept.value = "";
    Object.keys(approvalData).forEach((k) => delete approvalData[k]);
    storeVisitor();
    storeHost();
    storeApproval();
    updatePreview();
    bootstrap.Tab.getOrCreateInstance(
      document.querySelector("#visitor-tab"),
    ).show();
  }

  // visitor suggestions
  vName.addEventListener("input", async () => {
    const prefix = vName.value.trim();
    if (prefix.length < 2) {
      vNameList.innerHTML = "";
      return;
    }
    try {
      const r = await fetch(
        `/api/visitors/suggest?prefix=${encodeURIComponent(prefix)}`,
      );
      if (r.ok) {
        const data = await r.json();
        const list = data.suggestions || data;
        vNameList.innerHTML = "";
        (list || []).forEach((item) => {
          const name = item.name || item;
          const opt = document.createElement("option");
          opt.value = name;
          vNameList.appendChild(opt);
          if (typeof item === "object") visitorSuggestions[name] = item;
        });
      }
    } catch (err) {
      console.error("suggest", err);
    }
  });
  vName.addEventListener("change", () => {
    const info = visitorSuggestions[vName.value];
    if (!info) return;
    if (info.phone) {
      iti.setNumber(info.phone);
      vPhone.value = info.phone;
    }
    if (info.email) vEmail.value = info.email;
    if (info.visitor_type) {
      vType.value = info.visitor_type;
      if (typeSelect) {
        typeSelect.setValue(info.visitor_type);
      }
    }
    if (info.company) vCompany.value = info.company;
    storeVisitor();
    updatePreview();
  });

  // navigation
  document.getElementById("toPhoto").onclick = () => {
    let ok = true;
    if (!vName.value) {
      showFieldError(vName, "Required");
      ok = false;
    }
    if (!iti.isValidNumber()) {
      showFieldError(vPhone, "Invalid phone number");
      ok = false;
    }
    if (!validateEmail(vEmail.value)) {
      showFieldError(vEmail, "Invalid email");
      ok = false;
    }
    if (!vType.value) {
      showFieldError(vType, "Required");
      ok = false;
    }
    if (!vPurpose.value) {
      showFieldError(vPurpose, "Required");
      ok = false;
    }
    if (!vValid.value) {
      showFieldError(vValid, "Required");
      ok = false;
    } else if (new Date(vValid.value) < new Date()) {
      showFieldError(vValid, "Date/time cannot be in the past");
      ok = false;
    }
    if (!ok) {
      showToast("Please fix errors above", "danger");
      return;
    }
    bootstrap.Tab.getOrCreateInstance(
      document.querySelector("#photo-tab"),
    ).show();
  };
  document.getElementById("backVisitor").onclick = () =>
    bootstrap.Tab.getOrCreateInstance(
      document.querySelector("#visitor-tab"),
    ).show();
  toHostBtn.onclick = () => {
    if (!capturedInput.value && !(noPhotoChk && noPhotoChk.checked)) {
      showToast("Photo required", "danger");
      return;
    }
    bootstrap.Tab.getOrCreateInstance(
      document.querySelector("#host-tab"),
    ).show();
  };
  document.getElementById("backPhoto").onclick = () =>
    bootstrap.Tab.getOrCreateInstance(
      document.querySelector("#photo-tab"),
    ).show();
  document.getElementById("toReview").onclick = () => {
    let ok = true;
    if (!hName.value && !defaultHost) {
      showFieldError(hName, "Required");
      ok = false;
    }
    if (needApproval.checked && !approverEmail.value) {
      showFieldError(approverEmail, "Required");
      ok = false;
    }
    if (!ok) {
      showToast("Please fix errors above", "danger");
      return;
    }

    bootstrap.Tab.getOrCreateInstance(
      document.querySelector("#review-tab"),
    ).show();
    updatePreview();
  };
  document.getElementById("backHost").onclick = () =>
    bootstrap.Tab.getOrCreateInstance(
      document.querySelector("#host-tab"),
    ).show();

  // approval toggle
  needApproval.addEventListener("change", () => {
    approverBox.classList.toggle("d-none", !needApproval.checked);
    approverEmail.required = needApproval.checked;
    if (!needApproval.checked) {
      approverEmail.value = "";
      clearFieldError(approverEmail);
    }
    storeApproval();
  });

  // confirm save
  confirmBtn.onclick = () => {
    let ok = true;
    if (!vName.value) {
      showFieldError(vName, "Required");
      ok = false;
    }
    if (!iti.isValidNumber()) {
      showFieldError(vPhone, "Invalid phone number");
      ok = false;
    }
    if (!validateEmail(vEmail.value)) {
      showFieldError(vEmail, "Invalid email");
      ok = false;
    }
    if (!vType.value) {
      showFieldError(vType, "Required");
      ok = false;
    }
    if (!vPurpose.value) {
      showFieldError(vPurpose, "Required");
      ok = false;
    }
    if (!vValid.value) {
      showFieldError(vValid, "Required");
      ok = false;
    }
    if (!capturedInput.value && !(noPhotoChk && noPhotoChk.checked)) {
      showToast("Photo required", "danger");
      ok = false;
    }
    if (!hName.value && !defaultHost) {
      showFieldError(hName, "Required");
      ok = false;
    }
    if (needApproval.checked && !approverEmail.value) {
      showFieldError(approverEmail, "Required");
      ok = false;
    }
    if (!ok) {
      showToast("Please fix errors above", "danger");
      return;
    }

    updatePreview();
    confirmModal.show();
  };

  // save
  async function handleSave() {
    try {
      saveBtn.disabled = true;
      confirmModal.hide();
      storeVisitor();
      storeHost();
      storeApproval();
      const fd = new FormData();
      fd.append("name", visitorData.name);
      fd.append("phone", visitorData.phone);
      fd.append("email", visitorData.email);
      fd.append("visitor_type", visitorData.visitor_type);
      fd.append("purpose", visitorData.purpose);
      fd.append("company_name", visitorData.company);
      fd.append("valid_to", visitorData.valid_to);
      fd.append("host", hostData.name);
      fd.append("host_department", hostData.department);
      fd.append("needs_approval", approvalData.needsApproval ? "on" : "");
      fd.append("approver_email", approvalData.approverEmail);
      fd.append("captured", capturedInput.value);
      fd.append("invite_id", inviteId.value);
      if (noPhotoChk?.checked) {
        fd.append("no_photo", "on");
      }
      const r = await fetch("/gatepass/create", { method: "POST", body: fd });
      if (!r.ok) {
        const err = await r.text();
        showToast(`Save failed — ${err}`, "danger");
        return;
      }
      const d = await r.json();
      pGate.textContent = d.gate_id;
      pStatus.textContent = d.status || "Created";
      qrBox.innerHTML = '<img src="' + d.qr_img + '" alt="QR">';

      const printHandler = () => window.open(printBase + d.gate_id, "_blank");
      const pdfHandler = () => {
        const preview = document.getElementById("previewCard");
        const hidden = [];
        preview.querySelectorAll(".no-print").forEach((el) => {
          hidden.push([el, el.style.display]);
          el.style.display = "none";
        });
        html2pdf()
          .from(preview)
          .save(`gatepass_${d.gate_id}.pdf`)
          .then(() => hidden.forEach(([el, ds]) => (el.style.display = ds)));
      };
      const viewHandler = () =>
        window.open(`/gatepass/view/${d.gate_id}`, "_blank");
      const copyPassLinkHandler = () => {
        navigator.clipboard.writeText(`/gatepass/view/${d.gate_id}`);
        showToast("Pass link copied", "success");
      };
      const shareHandler = async () => {
        const url = `${location.origin}/gatepass/view/${d.gate_id}`;
        try {
          await navigator.clipboard.writeText(url);
        } catch {}
        if (navigator.share) {
          try {
            await navigator.share({ title: "Gate Pass", url });
          } catch {}
        } else {
          window.open(
            `mailto:?subject=Gate%20Pass&body=${encodeURIComponent(url)}`,
            "_blank",
          );
          window.open(
            `https://wa.me/?text=${encodeURIComponent(url)}`,
            "_blank",
          );
          showToast("Link copied", "success");
        }
      };

      printBtn.disabled = false;
      pdfBtn.disabled = false;
      viewBtn.disabled = false;
      shareBtn.disabled = false;

      printBtn.onclick = printHandler;
      pdfBtn.onclick = pdfHandler;
      viewBtn.onclick = viewHandler;
      shareBtn.onclick = shareHandler;

      copyPassLinkBtn.classList.remove("d-none");
      copyPassLinkBtn.onclick = copyPassLinkHandler;
      if (d.approval_url) {
        copyLinkBtn.classList.remove("d-none");
        copyLinkBtn.onclick = () => {
          navigator.clipboard.writeText(d.approval_url);
          showToast("Approval link copied", "success");
        };
      }

      const toastActions = `Gate Pass #${d.gate_id} created – What do you want to do next?<div class="mt-2 pt-2 border-top d-flex flex-wrap gap-2"><button class="btn btn-sm btn-light" id="toastPrint">Print</button><button class="btn btn-sm btn-light" id="toastView">View</button><button class="btn btn-sm btn-light" id="toastPdf">Download PDF</button><button class="btn btn-sm btn-light" id="toastShare">Share</button><button class="btn btn-sm btn-light" id="toastCopy">Copy Link</button></div>`;
      showToast(toastActions, "success");
      document.getElementById("toastPrint").onclick = printHandler;
      document.getElementById("toastView").onclick = viewHandler;
      document.getElementById("toastPdf").onclick = pdfHandler;
      document.getElementById("toastShare").onclick = shareHandler;
      document.getElementById("toastCopy").onclick = copyPassLinkHandler;

      newBtn.classList.remove("d-none");
      newBtn.onclick = resetGatePass;
    } catch (err) {
      showToast(`Save failed — ${err}`, "danger");
    } finally {
      saveBtn.disabled = false;
    }

    const bindSaveOnce = () => {
      saveBtn.removeEventListener("click", handleSave);
      saveBtn.addEventListener("click", handleSave, { once: true });
    };

    confirmModalEl.addEventListener("show.bs.modal", bindSaveOnce);
    confirmModalEl.addEventListener("hide.bs.modal", () =>
      saveBtn.removeEventListener("click", handleSave),
    );
  }
}
