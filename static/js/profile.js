document.addEventListener('DOMContentLoaded', () => {
  const form = document.querySelector('form');
  const nameField = document.getElementById('name');
  const photoField = document.getElementById('photo');
  const passwordField = document.getElementById('password');
  const fields = [nameField, photoField, passwordField];
  let isDirty = false;

  function showError(field, message) {
    const error = document.getElementById(field.id + 'Error');
    if (error) {
      error.textContent = message;
    }
    field.setAttribute('aria-invalid', message ? 'true' : 'false');
  }

  function clearError(field) {
    showError(field, '');
  }

  function validateName() {
    if (nameField.value.trim() === '') {
      showError(nameField, 'Name is required.');
      return false;
    }
    clearError(nameField);
    return true;
  }

  function validatePhoto() {
    const file = photoField.files[0];
    if (file && !file.type.startsWith('image/')) {
      showError(photoField, 'File must be an image.');
      return false;
    }
    clearError(photoField);
    return true;
  }

  function validatePassword() {
    if (passwordField.value && passwordField.value.length < 8) {
      showError(passwordField, 'Password must be at least 8 characters.');
      return false;
    }
    clearError(passwordField);
    return true;
  }

  fields.forEach((field) => {
    field.addEventListener('blur', () => {
      if (field === nameField) {
        validateName();
      } else if (field === photoField) {
        validatePhoto();
      } else if (field === passwordField) {
        validatePassword();
      }
    });

    field.addEventListener('change', () => {
      isDirty = true;
    });
  });

  form.addEventListener('submit', () => {
    isDirty = false;
  });

  window.addEventListener('beforeunload', (e) => {
    if (isDirty) {
      e.preventDefault();
      e.returnValue = '';
    }
  });
});


