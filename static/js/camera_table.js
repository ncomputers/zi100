// Purpose: camera table script

document.addEventListener("DOMContentLoaded", () => {
  document
    .querySelectorAll('[data-bs-toggle="tooltip"]')
    .forEach((el) => new bootstrap.Tooltip(el));

  const typeSelect = document.querySelector('select[name="type"]');
  const urlInput = document.getElementById("urlInput");

  function toggleLocal() {
    // URL input is used for all camera types including local devices.
    urlInput.placeholder =
      typeSelect.value === "local" ? "URL or device path" : "URL";
  }

  typeSelect.addEventListener("change", toggleLocal);
  toggleLocal();
});
