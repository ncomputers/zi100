// Purpose: User management interactions

const form = document.getElementById("addUser");
const addBtn = form.querySelector('button[type="submit"]');
const toastEl = document.getElementById("userToast");
const toastBody = toastEl.querySelector(".toast-body");
const showToast = (msg, variant = "success") => {
  toastEl.className = `toast text-bg-${variant} border-0`;
  toastBody.textContent = msg;
  bootstrap.Toast.getOrCreateInstance(toastEl).show();
};

form.addEventListener("submit", async (e) => {
  e.preventDefault();
  addBtn.disabled = true;
  const data = {
    username: form.username.value,
    password: form.password.value,
    role: form.role.value,
    modules: Array.from(form.modules.selectedOptions).map((o) => o.value),
  };
  try {
    const res = await fetch("/admin/users", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(data),
    });
    if (res.ok) {
      showToast("User added", "success");
      location.reload();
    } else {
      showToast("Failed to add user", "danger");
    }
  } catch (err) {
    showToast("Network error", "danger");
  }
  addBtn.disabled = false;
});

const table = document.getElementById("userTable");
table.querySelectorAll(".deleteUser").forEach((btn) => {
  btn.addEventListener("click", async (e) => {
    const row = e.target.closest("tr");
    const user = row.dataset.user;
    btn.disabled = true;
    try {
      const res = await fetch(`/admin/users/${user}`, { method: "DELETE" });
      if (res.ok) {
        row.remove();
        showToast("User deleted", "success");
      } else {
        showToast("Delete failed", "danger");
        btn.disabled = false;
      }
    } catch (err) {
      showToast("Network error", "danger");
      btn.disabled = false;
    }
  });
});

