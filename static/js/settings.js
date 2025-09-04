// Purpose: Settings page behavior

function getLastPathSegment(src) {
  const base =
    typeof window !== "undefined" ? window.location.href : "http://localhost";
  return new URL(src, base).pathname.split("/").pop();
}

if (typeof document !== "undefined" && !globalThis.__TEST__) {
  (function () {
    document.getElementById("cfgForm").addEventListener("submit", async (e) => {
      e.preventDefault();
      const form = new FormData(e.target);
      const btn = document.getElementById("cfgSaveBtn");
      const sp = document.getElementById("cfgSpinner");
      const msg = document.getElementById("msg");
      btn.disabled = true;
      sp.classList.remove("d-none");
      try {
        const r = await fetch("/settings", { method: "POST", body: form });
        if (!r.ok) throw new Error("Request failed");
        const type = r.headers.get("Content-Type") || "";
        if (r.redirected || !type.includes("application/json")) {
          location.href = r.url;
          return;
        }
        const d = await r.json();
        const toastEl = document.getElementById("saveToast");
        const body = toastEl.querySelector(".toast-body");
        if (d.saved) {
          body.textContent = "Settings saved successfully";
          toastEl.classList.remove("text-bg-danger");
          toastEl.classList.add("text-bg-success");
        } else {
          body.textContent = d.error || "Failed to save settings";
          toastEl.classList.remove("text-bg-success");
          toastEl.classList.add("text-bg-danger");
        }
        bootstrap.Toast.getOrCreateInstance(toastEl).show();
      } catch (err) {
        msg.innerHTML =
          '<div class="alert alert-danger">' + err.message + "</div>";
      } finally {
        sp.classList.add("d-none");
        btn.disabled = false;
      }
    });

    document.getElementById("resetBtn").addEventListener("click", async () => {
      const msg = document.getElementById("msg");
      msg.innerHTML = '<div class="spinner-border" role="status"></div>';
      try {
        const r = await fetch("/reset", { method: "POST" });
        if (!r.ok) throw new Error("Request failed");
        const d = await r.json();
        msg.innerHTML = d.reset
          ? ' <div class="alert alert-warning">Counts reset</div>'
          : '<div class="alert alert-danger">Error</div>';
      } catch (err) {
        msg.innerHTML =
          '<div class="alert alert-danger">' + err.message + "</div>";
      }
    });

    document
      .getElementById("activateLic")
      .addEventListener("click", async () => {
        const key = document.getElementById("licenseKey").value;
        const r = await fetch("/license", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ key }),
        });
        const d = await r.json();
        if (d.activated) {
          document.getElementById("licMsg").innerHTML =
            '<div class="alert alert-success">Activated</div>';
          if (d.info) {
            location.reload();
          }
        } else {
          document.getElementById("licMsg").innerHTML =
            '<div class="alert alert-danger">' +
            (d.error || "Error") +
            "</div>";
        }
      });

    document.getElementById("toggleKey").addEventListener("click", () => {
      const inp = document.getElementById("licenseKey");
      inp.type = inp.type === "password" ? "text" : "password";
    });

    const logoInput = document.querySelector("#logoInput");
    if (logoInput) {
      logoInput.onchange = (e) => {
        const file = e.target.files[0];
        if (!file) return;
        const url = URL.createObjectURL(file);
        const prev = document.getElementById("logo-preview");
        if (prev) {
          prev.src = url;
          prev.style.display = "block";
        }
        const nav = document.getElementById("navbar-logo");
        if (nav) nav.src = url;
      };
    }

    const footerLogoInput = document.querySelector("#footerLogoInput");
    if (footerLogoInput) {
      footerLogoInput.onchange = (e) => {
        const file = e.target.files[0];
        if (!file) return;
        const url = URL.createObjectURL(file);
        const prev = document.getElementById("footer-logo-preview");
        if (prev) {
          prev.src = url;
          prev.style.display = "block";
        }
      };
    }

    function updateEmailTest() {
      const section = document.getElementById("emailTestSection");
      if (!section) return;
      const host = document
        .querySelector('input[name="smtp_host"]')
        ?.value.trim();
      const from = document
        .querySelector('input[name="from_addr"]')
        ?.value.trim();
      if (host && from) section.classList.remove("d-none");
      else section.classList.add("d-none");
    }

    ["smtp_host", "from_addr"].forEach((name) => {
      const el = document.querySelector(`[name="${name}"]`);
      if (el) el.addEventListener("input", updateEmailTest);
    });
    updateEmailTest();

    const bufRange = document.getElementById("captureBufferRange");
    const bufInput = document.getElementById("captureBufferInput");
    if (bufRange && bufInput) {
      bufRange.addEventListener("input", () => {
        bufInput.value = bufRange.value;
      });
      bufInput.addEventListener("input", () => {
        bufRange.value = bufInput.value;
      });
    }

    const testBtn = document.getElementById("emailTestBtn");
    if (testBtn) {
      testBtn.addEventListener("click", async () => {
        const addr = document.getElementById("testEmailRecipient").value;
        const msgEl = document.getElementById("emailMsg");
        msgEl.innerHTML = '<div class="spinner-border" role="status"></div>';
        try {
          const get = (n) => document.querySelector(`[name="${n}"]`);
          const payload = { recipient: addr };
          [
            "smtp_host",
            "smtp_port",
            "smtp_user",
            "smtp_pass",
            "use_tls",
            "use_ssl",
            "from_addr",
          ].forEach((name) => {
            const el = get(name);
            if (!el) return;
            let val;
            if (el.type === "checkbox") val = el.checked;
            else val = el.value.trim();
            if (name === "smtp_port") {
              const n = parseInt(val, 10);
              if (!Number.isNaN(n)) val = n;
              else return;
            }
            if (val !== "" && val !== undefined) payload[name] = val;
          });
          const r = await fetch("/settings/email/test", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(payload),
          });
          const d = await r.json();
          if (d.sent) {
            msgEl.innerHTML =
              '<div class="alert alert-success">Test Sent</div>';
          } else {
            const errMap = {
              missing_recipient: "Recipient required",
              missing_smtp_host: "SMTP host not configured",
            };
            const errText = errMap[d.error] || d.error || "Error";
            msgEl.innerHTML =
              '<div class="alert alert-danger">' + errText + "</div>";
          }
        } catch (err) {
          msgEl.innerHTML =
            '<div class="alert alert-danger">' + err.message + "</div>";
        }
      });
    }

    const tab = new URLSearchParams(location.search).get("tab");
    if (tab === "branding") {
      const coll = document.querySelector("#brand");
      if (coll) new bootstrap.Collapse(coll, { toggle: true });
    }

    document.getElementById("exportCfg").addEventListener("click", () => {
      window.location = "/settings/export";
    });

    document
      .getElementById("importFile")
      .addEventListener("change", async (e) => {
        const file = e.target.files[0];
        if (!file) return;
        const msg = document.getElementById("msg");
        msg.innerHTML = '<div class="spinner-border" role="status"></div>';
        try {
          const data = JSON.parse(await file.text());
          const r = await fetch("/settings/import", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(data),
          });
          if (!r.ok) throw new Error("Request failed");
          const d = await r.json();
          msg.innerHTML = d.saved
            ? '<div class="alert alert-success">Imported</div>'
            : '<div class="alert alert-danger">Error</div>';
        } catch (err) {
          msg.innerHTML =
            '<div class="alert alert-danger">' + err.message + "</div>";
        }
      });

    document
      .querySelectorAll('[data-bs-toggle="tooltip"]')
      .forEach((el) => new bootstrap.Tooltip(el));

    document
      .querySelectorAll(".toggle-card .form-check-input")
      .forEach((inp) => {
        const card = inp.closest(".toggle-card");
        const update = () =>
          card.classList.toggle("border-primary", inp.checked);
        update();
        inp.addEventListener("change", update);
      });

    const debugIds = [
      "showLines",
      "showIds",
      "showTrackLines",
      "showCounts",
      "showFaceBoxes",
    ];
    const feeds = document.querySelectorAll("img.feed-img");

    function updateFeeds() {
      const debug = debugIds.some((id) => document.getElementById(id)?.checked);
      feeds.forEach((img) => {
        const cam = getLastPathSegment(img.src);
        const base = "/stream/";
        const target = debug ? base + cam : base + cam + "?raw=1";
        if (img.src.endsWith(target)) return;
        img.src = target;
      });
      if (feeds.length) {
        const msg = document.getElementById("msg");
        if (msg)
          msg.innerHTML =
            '<div class="alert alert-info">Camera feeds updated</div>';
      }
    }

    debugIds.forEach((id) => {
      const el = document.getElementById(id);
      if (el) el.addEventListener("change", updateFeeds);
    });
  })();
}

if (typeof module !== "undefined") {
  module.exports = { getLastPathSegment };
}
