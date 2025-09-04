// Handles avatar upload with drag-drop and CropperJS.
document.addEventListener('DOMContentLoaded', () => {
  const drop = document.getElementById('avatar-drop');
  const input = document.getElementById('photo');
  const preview = document.getElementById('avatar-preview');
  const removeInput = document.getElementById('remove_photo');
  const replaceBtn = document.getElementById('replaceBtn');
  const removeBtn = document.getElementById('removeBtn');
  const resetBtn = document.getElementById('resetBtn');
  const modalEl = document.getElementById('cropModal');
  const modalImg = document.getElementById('cropImg');
  const cropSave = document.getElementById('cropSave');
  const bsModal = new bootstrap.Modal(modalEl);
  const original = preview.innerHTML;
  const originalPhoto = preview.querySelector('img')?.src || null;
  const initials = originalPhoto ? null : preview.textContent.trim();
  let cropper = null;

  function showInitials() {
    if (initials) {
      preview.innerHTML = initials;
    } else {
      preview.innerHTML = '';
    }
  }

  function setPreview(url) {
    preview.innerHTML = `<img src="${url}" style="width:100%;height:100%;object-fit:cover;" alt="avatar">`;
  }

  function reset() {
    input.value = '';
    removeInput.value = '0';
    if (originalPhoto) {
      setPreview(originalPhoto);
    } else {
      showInitials();
    }
  }

  function handleFile(file) {
    if (!file.type.match(/^image\/(png|jpeg)$/)) {
      alert('Only JPG/PNG allowed');
      return;
    }
    if (file.size > 4 * 1024 * 1024) {
      alert('File too large');
      return;
    }
    const reader = new FileReader();
    reader.onload = () => {
      modalImg.src = reader.result;
      bsModal.show();
    };
    reader.readAsDataURL(file);
    cropSave.onclick = () => {
      if (!cropper) return;
      const canvas = cropper.getCroppedCanvas({ width: 256, height: 256 });
      canvas.toBlob((blob) => {
        const dt = new DataTransfer();
        dt.items.add(new File([blob], 'avatar.jpg', { type: 'image/jpeg' }));
        input.files = dt.files;
        setPreview(canvas.toDataURL('image/jpeg'));
        removeInput.value = '0';
      }, 'image/jpeg', 0.9);
      bsModal.hide();
    };
  }

  modalEl.addEventListener('shown.bs.modal', () => {
    cropper = new Cropper(modalImg, { aspectRatio: 1, viewMode: 1 });
  });
  modalEl.addEventListener('hidden.bs.modal', () => {
    cropper?.destroy();
    cropper = null;
  });

  drop.addEventListener('click', () => input.click());
  drop.addEventListener('dragover', (e) => {
    e.preventDefault();
    drop.classList.add('bg-light');
  });
  drop.addEventListener('dragleave', () => drop.classList.remove('bg-light'));
  drop.addEventListener('drop', (e) => {
    e.preventDefault();
    drop.classList.remove('bg-light');
    const file = e.dataTransfer.files[0];
    if (file) handleFile(file);
  });

  input.addEventListener('change', (e) => {
    const file = e.target.files[0];
    if (file) handleFile(file);
  });

  replaceBtn.addEventListener('click', () => input.click());
  removeBtn.addEventListener('click', () => {
    reset();
    removeInput.value = '1';
  });
  resetBtn.addEventListener('click', () => reset());
});
