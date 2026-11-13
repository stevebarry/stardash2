// Shared helpers for the BI Dashboard pages.

async function api(method, url, body) {
  const opts = { method, headers: {} };
  if (body !== undefined) {
    opts.headers["Content-Type"] = "application/json";
    opts.body = JSON.stringify(body);
  }
  const res = await fetch(url, opts);
  if (res.status === 401) {
    window.location = "/login?next=" + encodeURIComponent(window.location.pathname);
    throw new Error("Not logged in");
  }
  const type = res.headers.get("Content-Type") || "";
  if (!res.ok) {
    let msg = res.statusText;
    if (type.includes("application/json")) msg = (await res.json()).error || msg;
    throw new Error(msg);
  }
  return type.includes("application/json") ? res.json() : res.blob();
}

function el(tag, attrs, ...children) {
  const node = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (v === null || v === undefined || v === false) continue;
    if (k === "class") node.className = v;
    else if (k.startsWith("on")) node.addEventListener(k.slice(2), v);
    else node.setAttribute(k, v === true ? "" : v);
  }
  for (const c of children.flat()) {
    if (c === null || c === undefined) continue;
    node.append(c instanceof Node ? c : document.createTextNode(String(c)));
  }
  return node;
}

function showError(form, message) {
  const p = form.querySelector(".error");
  p.textContent = message || "";
  p.hidden = !message;
}

// Wire "Cancel" buttons inside dialogs.
document.addEventListener("click", (e) => {
  if (e.target.matches("dialog button[value=cancel]")) e.target.closest("dialog").close();
});
