// Dashboard list: create and delete dashboards (admin only controls).

document.querySelectorAll(".delete-dashboard").forEach((btn) => {
  btn.addEventListener("click", async () => {
    if (!confirm(`Delete dashboard "${btn.dataset.name}"? This cannot be undone.`)) return;
    try {
      await api("DELETE", `/api/dashboards/${btn.dataset.id}`);
      btn.closest("li").remove();
    } catch (err) {
      alert(err.message);
    }
  });
});

const newBtn = document.getElementById("new-dashboard");
if (newBtn) {
  const dialog = document.getElementById("new-dashboard-dialog");
  const form = document.getElementById("new-dashboard-form");

  newBtn.addEventListener("click", async () => {
    showError(form, "");
    form.reset();
    try {
      const [views, roles] = await Promise.all([api("GET", "/api/views"), api("GET", "/api/roles")]);
      form.view.replaceChildren(el("option", { value: "" }, "Select a view…"),
        ...views.map((v) => el("option", { value: v }, v)));
      form.roles.replaceChildren(...roles.map((r) => el("option", { value: r }, r)));
      dialog.showModal();
    } catch (err) {
      alert(err.message);
    }
  });

  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    const body = {
      view: form.view.value,
      name: form.dashboard_name.value.trim(),
      roles: [...form.roles.selectedOptions].map((o) => o.value),
    };
    try {
      const res = await api("POST", "/api/dashboards", body);
      window.location = `/dashboard/${res.id}`;
    } catch (err) {
      showError(form, err.message);
    }
  });
}
