// Dashboard screen: filters, KPI/chart/table widgets and export.

const DASH = window.DASHBOARD_ID;
const PALETTE = ["#2563eb", "#f59e0b", "#10b981", "#ef4444", "#8b5cf6",
                 "#06b6d4", "#ec4899", "#84cc16", "#f97316", "#64748b", "#a3a3a3"];
const CHART_TYPE_LABELS = {
  bar: "Bar", stacked_bar: "Stacked bar", horizontal_bar: "Horizontal bar",
  line: "Line", area: "Area", pie: "Pie", doughnut: "Doughnut",
};

let meta = null;
const widgets = new Map();  // item id -> {item, card, chart, data}
const state = { period: "", start: "", end: "", filters: {} };

// ---- formatting -----------------------------------------------------------

const numberFmt = new Intl.NumberFormat(undefined, { maximumFractionDigits: 2 });
const euroFmt = new Intl.NumberFormat(undefined, { style: "currency", currency: "EUR", maximumFractionDigits: 2 });
const euroFmt0 = new Intl.NumberFormat(undefined, { style: "currency", currency: "EUR", maximumFractionDigits: 0 });

function fmtValue(v, isEuro) {
  if (v === null || v === undefined) return "–";
  if (isEuro) return Math.abs(v) >= 1000 ? euroFmt0.format(v) : euroFmt.format(v);
  return numberFmt.format(v);
}

function colLabel(col) {
  if (!col) return "";
  let label = col.replace(/^(euro_|ms_|date_)/i, "").replace(/_/g, " ");
  label = label.charAt(0).toUpperCase() + label.slice(1);
  return /^euro_/i.test(col) ? `${label} (€)` : label;
}

// Charts saved before multi-measure support store a single `measure`.
const chartMeasures = (cfg) => cfg.measures || (cfg.measure ? [cfg.measure] : []);

function defaultTitle(type, cfg) {
  if (type === "kpi") return colLabel(cfg.measure);
  if (type === "chart") {
    const x = cfg.x_axis || cfg.group_by; // group_by: charts saved before the x-axis rename
    let t = `${chartMeasures(cfg).map(colLabel).join(", ")} by ${colLabel(x)}`;
    if (x === meta.columns.date) t += ` (${cfg.grain || "month"})`;
    if (cfg.breakdown) t += ` and ${colLabel(cfg.breakdown)}`;
    return t;
  }
  return "Table";
}

const titleOf = (item) => item.config.title || defaultTitle(item.item_type, item.config);

// ---- filters --------------------------------------------------------------

function buildFilters() {
  const periodSel = document.getElementById("f-period");
  for (const p of meta.periods) periodSel.append(el("option", { value: p.key }, p.label));
  // choosing a period applies it at once, so KPIs show the % change without pressing Apply
  periodSel.addEventListener("change", () => {
    fillPeriodDates();
    if (periodSel.value) applyFilters();
  });
  for (const id of ["f-start", "f-end"]) {
    document.getElementById(id).addEventListener("input", () => { periodSel.value = ""; });
  }
  if (!meta.columns.date) {
    document.querySelector(".date-filter").hidden = true;
  }

  const container = document.getElementById("attr-filters");
  for (const attr of meta.columns.attributes) {
    const values = meta.filter_values[attr] || [];
    const summary = el("summary", {}, colLabel(attr));
    const search = el("input", { type: "search", placeholder: "Search…", class: "filter-search" });
    const list = el("div", { class: "filter-options" },
      values.map((v) => el("label", {}, el("input", { type: "checkbox", value: v, "data-attr": attr }), v)));
    search.addEventListener("input", () => {
      const q = search.value.toLowerCase();
      list.querySelectorAll("label").forEach((l) => { l.hidden = !l.textContent.toLowerCase().includes(q); });
    });
    const clear = el("button", { type: "button", class: "link", onclick: () => {
      list.querySelectorAll("input").forEach((i) => { i.checked = false; });
      updateFilterSummary(details, attr);
    } }, "Clear");
    const details = el("details", { class: "dropdown", "data-attr": attr }, summary,
      el("div", { class: "dropdown-panel" }, search, list, clear));
    list.addEventListener("change", () => updateFilterSummary(details, attr));
    container.append(details);
  }
  // close other dropdowns when one opens
  container.addEventListener("toggle", (e) => {
    if (e.target.open) container.querySelectorAll("details[open]").forEach((d) => { if (d !== e.target) d.open = false; });
  }, true);

  document.getElementById("f-apply").addEventListener("click", applyFilters);
  document.getElementById("f-reset").addEventListener("click", () => {
    periodSel.value = "";
    document.getElementById("f-start").value = "";
    document.getElementById("f-end").value = "";
    container.querySelectorAll("input[type=checkbox]").forEach((i) => { i.checked = false; });
    container.querySelectorAll("details").forEach((d) => updateFilterSummary(d, d.dataset.attr));
    applyFilters();
  });
}

function fillPeriodDates() {
  const p = meta.periods.find((x) => x.key === document.getElementById("f-period").value);
  if (p) {
    document.getElementById("f-start").value = p.start;
    document.getElementById("f-end").value = p.end;
  }
}

function updateFilterSummary(details, attr) {
  const n = details.querySelectorAll("input[type=checkbox]:checked").length;
  details.querySelector("summary").textContent = n ? `${colLabel(attr)} (${n})` : colLabel(attr);
  details.classList.toggle("active", n > 0);
}

// Copy the filter controls into `state` (what is shown is what gets queried).
function readFilterControls() {
  state.period = document.getElementById("f-period").value;
  state.start = document.getElementById("f-start").value;
  state.end = document.getElementById("f-end").value;
  state.filters = {};
  document.querySelectorAll("#attr-filters input[type=checkbox]:checked").forEach((i) => {
    (state.filters[i.dataset.attr] ||= []).push(i.value);
  });
}

function applyFilters() {
  readFilterControls();
  document.querySelectorAll("#attr-filters details[open]").forEach((d) => { d.open = false; });
  refreshAll();
}

function filterSummary() {
  const lines = [];
  if (state.period) {
    const p = meta.periods.find((x) => x.key === state.period);
    lines.push(`Period: ${p.label} (${p.start} to ${p.end})`);
  } else if (state.start || state.end) {
    lines.push(`Dates: ${state.start || "…"} to ${state.end || "…"}`);
  }
  for (const [attr, vals] of Object.entries(state.filters)) lines.push(`${colLabel(attr)}: ${vals.join(", ")}`);
  if (!lines.length) lines.push("No filters applied");
  return lines;
}

// ---- widgets --------------------------------------------------------------

function renderWidget(item) {
  const existing = widgets.get(item.id);
  if (existing && existing.chart) existing.chart.destroy();

  const width = item.item_type === "kpi" ? "kpi" : item.width;
  const actions = el("div", { class: "widget-actions" },
    item.item_type !== "kpi" ? el("button", { class: "icon", title: "Toggle full / half width", onclick: () => toggleWidth(item.id) },
      item.width === "full" ? "⇥⇤" : "⇤⇥") : null,
    item.item_type === "table" ? el("button", { class: "icon", title: "Export to CSV", onclick: () => exportCsv(item.id) }, "⤓") : null,
    el("button", { class: "icon", title: "Edit", onclick: () => openItemDialog(item.item_type, item) }, "✎"),
    el("button", { class: "icon", title: "Remove", onclick: () => removeItem(item.id) }, "✕"));
  const body = el("div", { class: "widget-body" }, el("div", { class: "muted" }, "Loading…"));
  const card = el("article", { class: `widget card ${item.item_type} ${width}`, "data-id": item.id },
    el("header", {}, el("h3", {}, titleOf(item)), actions), body);

  if (existing) existing.card.replaceWith(card);
  else document.getElementById("widgets").append(card);
  widgets.set(item.id, { item, card, chart: null, data: null });
  loadWidget(item.id);
}

async function loadWidget(id) {
  const w = widgets.get(id);
  const body = w.card.querySelector(".widget-body");
  try {
    const data = await api("POST", `/api/dashboards/${DASH}/data`, {
      item_type: w.item.item_type, config: w.item.config,
      period: state.period, start: state.start, end: state.end, filters: state.filters,
    });
    if (widgets.get(id) !== w) return;  // replaced while loading
    w.data = data;
    body.replaceChildren();
    if (w.item.item_type === "kpi") drawKpi(body, data);
    else if (w.item.item_type === "chart") drawChart(w, body, data);
    else drawTable(body, data);
  } catch (err) {
    body.replaceChildren(el("div", { class: "error" }, err.message));
  }
}

function kpiTexts(data) {
  const texts = { value: fmtValue(data.value, data.is_euro), change: "", previous: "", dir: "" };
  if (state.period) {
    if (data.pct_change === null || data.pct_change === undefined) {
      texts.change = "n/a";
    } else {
      texts.dir = data.pct_change > 0 ? "up" : data.pct_change < 0 ? "down" : "flat";
      const arrow = { up: "▲", down: "▼", flat: "■" }[texts.dir];
      texts.change = `${arrow} ${Math.abs(data.pct_change).toFixed(1)}%`;
    }
    texts.previous = `vs ${fmtValue(data.previous, data.is_euro)} (${data.previous_start} – ${data.previous_end})`;
  }
  return texts;
}

function drawKpi(body, data) {
  const t = kpiTexts(data);
  body.append(el("div", { class: "kpi-value" }, t.value));
  if (state.period) {
    body.append(el("div", { class: `kpi-change ${t.dir}` }, t.change),
                el("div", { class: "kpi-prev muted" }, t.previous));
  }
}

const whiteBackground = {
  id: "whiteBackground",
  beforeDraw(chart) {
    const { ctx } = chart;
    ctx.save();
    ctx.globalCompositeOperation = "destination-over";
    ctx.fillStyle = "#ffffff";
    ctx.fillRect(0, 0, chart.width, chart.height);
    ctx.restore();
  },
};

function drawChart(w, body, data) {
  const cfg = w.item.config;
  const type = cfg.chart_type;
  const canvas = el("canvas");
  body.append(el("div", { class: "chart-box" }, canvas));
  if (!data.labels.length) {
    body.replaceChildren(el("div", { class: "muted" }, "No data for the current filters"));
    return;
  }
  const isPie = type === "pie" || type === "doughnut";
  const horizontal = type === "horizontal_bar";
  const multiMeasure = new Set(data.datasets.map((d) => d.measure)).size > 1;
  const hasBreakdown = data.datasets.some((d) => d.series !== null);
  // € and plain measures on one chart get separate value axes
  const anyEuro = data.datasets.some((d) => d.is_euro);
  const mixed = anyEuro && data.datasets.some((d) => !d.is_euro);
  const valueKey = horizontal ? "x" : "y";
  const stackedArea = type === "area" && hasBreakdown && !multiMeasure;
  const stacked = type === "stacked_bar" || stackedArea;

  let datasets;
  if (isPie) {
    const d0 = data.datasets[0];
    datasets = [{ label: colLabel(d0.measure), data: d0.data, isEuro: d0.is_euro,
                  backgroundColor: data.labels.map((_, i) => PALETTE[i % PALETTE.length]) }];
  } else {
    datasets = data.datasets.map((d, i) => {
      const color = PALETTE[i % PALETTE.length];
      let label = colLabel(d.measure);
      if (d.series !== null) label = multiMeasure ? `${label} · ${d.series}` : d.series;
      return {
        label,
        data: d.data,
        isEuro: d.is_euro,
        stack: d.measure,  // stacked bars: one stack per measure
        [`${valueKey}AxisID`]: mixed && !d.is_euro ? `${valueKey}1` : valueKey,
        backgroundColor: color + (type === "area" ? "66" : ""),
        borderColor: color,
        fill: type === "area" ? (stackedArea && i > 0 ? "-1" : "origin") : false,
        tension: 0.2,
        pointRadius: data.labels.length > 60 ? 0 : 3,
      };
    });
  }

  const valueAxis = (euro) => ({ stacked, beginAtZero: true, ticks: { callback: (v) => fmtValue(v, euro) } });
  const scales = {};
  if (!isPie) {
    scales[horizontal ? "y" : "x"] = { stacked };
    scales[valueKey] = valueAxis(anyEuro);
    if (mixed) {
      scales[`${valueKey}1`] = { ...valueAxis(false), position: horizontal ? "top" : "right",
                                 grid: { drawOnChartArea: false } };
    }
  }
  w.chart = new Chart(canvas, {
    type: isPie ? type : (type === "line" || type === "area") ? "line" : "bar",
    data: { labels: data.labels, datasets },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      animation: false,
      indexAxis: horizontal ? "y" : "x",
      plugins: {
        legend: { display: isPie || datasets.length > 1, position: "bottom" },
        tooltip: { callbacks: { label: (c) => `${c.dataset.label}: ${fmtValue(c.raw, c.dataset.isEuro)}` } },
      },
      scales,
    },
    plugins: [whiteBackground],
  });
}

function tableTexts(data) {
  const euro = new Set(data.euro_columns);
  const meas = new Set(data.measure_columns);
  return {
    columns: data.columns.map(colLabel),
    rows: data.rows.map((r) => r.map((v, i) => {
      const c = data.columns[i];
      if (meas.has(c)) return fmtValue(v, euro.has(c));
      return v === null ? "(blank)" : String(v);
    })),
    numeric: data.columns.map((c) => meas.has(c)),
  };
}

function drawTable(body, data) {
  const t = tableTexts(data);
  if (!t.rows.length) {
    body.append(el("div", { class: "muted" }, "No data for the current filters"));
    return;
  }
  const table = el("table", { class: "data-table" },
    el("thead", {}, el("tr", {}, t.columns.map((c, i) => el("th", { class: t.numeric[i] ? "num" : null }, c)))),
    el("tbody", {}, t.rows.map((r) => el("tr", {}, r.map((v, i) => el("td", { class: t.numeric[i] ? "num" : null }, v))))));
  body.append(el("div", { class: "table-wrap" }, table));
}

// Quote every cell; text starting with a formula character is prefixed with ' so spreadsheets don't run it.
function csvCell(v) {
  let s = v === null || v === undefined ? "" : String(v);
  if (typeof v === "string" && /^[=+\-@\t\r]/.test(s)) s = `'${s}`;
  return `"${s.replace(/"/g, '""')}"`;
}

// Exports the rows the table has loaded, with raw (unformatted) measure values.
function exportCsv(id) {
  const w = widgets.get(id);
  if (!w || !w.data) {
    setStatus("Table is still loading");
    return;
  }
  const meas = new Set(w.data.measure_columns);
  const lines = [w.data.columns.map(colLabel), ...w.data.rows.map((r) => r.map((v, i) =>
    v === null && !meas.has(w.data.columns[i]) ? "(blank)" : v))];
  const csv = "\uFEFF" + lines.map((r) => r.map(csvCell).join(",")).join("\r\n") + "\r\n";
  const name = `${meta.dashboard.name} - ${titleOf(w.item)}`.replace(/[^A-Za-z0-9 _.-]+/g, "_");
  downloadBlob(new Blob([csv], { type: "text/csv;charset=utf-8" }), `${name}.csv`);
}

function downloadBlob(blob, filename) {
  const url = URL.createObjectURL(blob);
  const a = el("a", { href: url, download: filename });
  document.body.append(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 10000);
}

function refreshAll() {
  for (const id of widgets.keys()) loadWidget(id);
}

async function toggleWidth(id) {
  const w = widgets.get(id);
  const width = w.item.width === "full" ? "half" : "full";
  try {
    const updated = await api("PATCH", `/api/items/${id}`, { width });
    renderWidget(updated);
  } catch (err) {
    alert(err.message);
  }
}

async function removeItem(id) {
  if (!confirm("Remove this item from the dashboard?")) return;
  try {
    await api("DELETE", `/api/items/${id}`);
    const w = widgets.get(id);
    if (w.chart) w.chart.destroy();
    w.card.remove();
    widgets.delete(id);
  } catch (err) {
    alert(err.message);
  }
}

// ---- add / edit dialog ------------------------------------------------------

const dialog = document.getElementById("item-dialog");
const form = document.getElementById("item-form");
const fields = document.getElementById("item-fields");
let dialogCtx = null;  // {type, item}

function selectField(name, label, options, value, { optional = false } = {}) {
  const sel = el("select", { name },
    optional ? el("option", { value: "" }, "(none)") : null,
    options.map((o) => el("option", { value: o, selected: o === value }, colLabel(o))));
  return el("label", {}, label, sel);
}

// The main date is offered once per time subdivision; option values are "column|grain".
function axisField(name, label, cfg, value, { optional = false } = {}) {
  const date = meta.columns.date;
  const grain = cfg.grain || "month";
  const sel = el("select", { name },
    optional ? el("option", { value: "" }, "(none)") : null,
    date ? meta.grains.map((g) => el("option", { value: `${date}|${g}`, selected: value === date && g === grain },
      `${colLabel(date)} by ${g}`)) : null,
    meta.columns.attributes.map((o) => el("option", { value: o, selected: o === value }, colLabel(o))));
  return el("label", {}, label, sel);
}

const splitAxis = (value) => (value ? value.split("|") : [null, null]);

function checkboxGroup(name, label, options, values) {
  return el("fieldset", {}, el("legend", {}, label),
    options.map((o) => el("label", { class: "check" },
      el("input", { type: "checkbox", name, value: o, checked: values.includes(o) }), colLabel(o))));
}

function openItemDialog(type, item) {
  dialogCtx = { type, item };
  showError(form, "");
  const cfg = item ? item.config : {};
  const title = { kpi: "KPI", chart: "Chart", table: "Table" }[type];
  document.getElementById("item-dialog-title").textContent = (item ? "Edit " : "Add ") + title;
  document.getElementById("item-submit").hidden = false;

  if (!meta.columns.euro.length && !meta.columns.measures.length && type !== "table") {
    fields.replaceChildren(el("p", { class: "error" }, "This view has no euro_ or ms_ measure columns."));
    document.getElementById("item-submit").hidden = true;
  } else if (type === "chart" && !item) {
    chartTypeStep();
  } else {
    fillFields(type, cfg);
  }
  dialog.showModal();
}

function chartTypeStep() {
  document.getElementById("item-submit").hidden = true;
  fields.replaceChildren(el("p", {}, "What type of chart?"),
    el("div", { class: "chart-type-grid" }, meta.chart_types.map((t) =>
      el("button", { type: "button", class: "chart-type", onclick: () => {
        document.getElementById("item-submit").hidden = false;
        fillFields("chart", { chart_type: t });
      } }, CHART_TYPE_LABELS[t] || t))));
}

function fillFields(type, cfg) {
  const measures = [...meta.columns.euro, ...meta.columns.measures];
  const groupCols = [...(meta.columns.date ? [meta.columns.date] : []), ...meta.columns.attributes];
  const titleInput = el("label", {}, "Title (optional)",
    el("input", { name: "item_title", value: cfg.title || "", maxlength: 200, placeholder: "Automatic" }));

  fields.onchange = null;
  if (type === "kpi") {
    fields.replaceChildren(titleInput, selectField("measure", "Measure", measures, cfg.measure));
  } else if (type === "chart") {
    const typeSel = el("label", {}, "Chart type", el("select", { name: "chart_type" },
      meta.chart_types.map((t) => el("option", { value: t, selected: t === cfg.chart_type }, CHART_TYPE_LABELS[t] || t))));
    const breakdown = axisField("breakdown", "Breakdown", cfg, cfg.breakdown, { optional: true });
    breakdown.classList.add("breakdown");
    const saved = chartMeasures(cfg);
    const pieHint = el("small", { class: "muted" }, "Pie and doughnut charts show one measure.");
    fields.replaceChildren(titleInput, typeSel,
      axisField("x_axis", "X-axis", cfg, cfg.x_axis || cfg.group_by), breakdown,
      checkboxGroup("measures", "Measures", measures, saved.length ? saved : measures.slice(0, 1)), pieHint);
    const sync = () => {
      const isPie = ["pie", "doughnut"].includes(form.chart_type.value);
      breakdown.hidden = isPie;
      pieHint.hidden = !isPie;
      if (isPie) form.breakdown.value = "";
    };
    fields.onchange = sync;
    sync();
  } else {
    fields.replaceChildren(titleInput,
      checkboxGroup("dimensions", "Group by columns", groupCols, cfg.dimensions || []),
      checkboxGroup("measures", "Measures", measures, cfg.measures || measures.slice(0, 1)));
  }
}

function readFields() {
  const { type } = dialogCtx;
  const cfg = { title: form.item_title.value.trim() };
  const checked = (name) => [...form.querySelectorAll(`input[name=${name}]:checked`)].map((i) => i.value);
  if (type === "kpi") cfg.measure = form.measure.value;
  else if (type === "chart") {
    const [x, xGrain] = splitAxis(form.x_axis.value);
    const [breakdown, bGrain] = splitAxis(form.breakdown.value);
    Object.assign(cfg, { chart_type: form.chart_type.value, x_axis: x, breakdown,
      measures: checked("measures"), grain: xGrain || bGrain || "month" });
  } else {
    cfg.dimensions = checked("dimensions");
    cfg.measures = checked("measures");
  }
  return cfg;
}

form.addEventListener("submit", async (e) => {
  e.preventDefault();
  const { type, item } = dialogCtx;
  const config = readFields();
  try {
    const saved = item
      ? await api("PATCH", `/api/items/${item.id}`, { config })
      : await api("POST", `/api/dashboards/${DASH}/items`, { item_type: type, config, width: type === "table" ? "full" : "half" });
    dialog.close();
    setStatus("");
    renderWidget(saved);
  } catch (err) {
    showError(form, err.message);
  }
});

document.querySelectorAll("[data-add]").forEach((b) =>
  b.addEventListener("click", () => openItemDialog(b.dataset.add, null)));

// ---- export -------------------------------------------------------------------

const exportBtn = document.getElementById("export-btn");
const exportMenu = document.getElementById("export-menu");
exportBtn.addEventListener("click", (e) => { e.stopPropagation(); exportMenu.hidden = !exportMenu.hidden; });
document.addEventListener("click", () => { exportMenu.hidden = true; });

// Redraw the chart at (at least) 2x resolution for the snapshot so it stays sharp when printed.
function chartPng(chart) {
  const ratio = chart.options.devicePixelRatio;
  chart.options.devicePixelRatio = Math.max(2, window.devicePixelRatio || 1);
  chart.resize();
  chart.update("none");
  const png = chart.toBase64Image("image/png");
  chart.options.devicePixelRatio = ratio;
  chart.resize();
  chart.update("none");
  return png;
}

exportMenu.querySelectorAll("[data-export]").forEach((b) => b.addEventListener("click", async () => {
  const format = b.dataset.export;
  const items = [];
  for (const { item, chart, data } of widgets.values()) {
    if (!data) continue;
    const title = titleOf(item);
    if (item.item_type === "kpi") {
      const t = kpiTexts(data);
      items.push({ type: "kpi", title, value_text: t.value, change_text: t.change, previous_text: t.previous, dir: t.dir });
    } else if (item.item_type === "chart") {
      if (chart) items.push({ type: "chart", title, png: chartPng(chart), width: item.width });
    } else {
      const t = tableTexts(data);
      items.push({ type: "table", title, columns: t.columns, rows: t.rows, numeric: t.numeric, width: item.width });
    }
  }
  setStatus(`Preparing ${format === "pdf" ? "PDF" : "Word"} export…`);
  try {
    const blob = await api("POST", `/api/dashboards/${DASH}/export?format=${format}`,
      { filter_summary: filterSummary(), items });
    downloadBlob(blob, `${meta.dashboard.name}.${format}`);
    setStatus("");
  } catch (err) {
    setStatus(`Export failed: ${err.message}`);
  }
}));

function setStatus(text) {
  document.getElementById("status").textContent = text;
}

// ---- init -----------------------------------------------------------------

(async function init() {
  setStatus("Loading…");
  try {
    meta = await api("GET", `/api/dashboards/${DASH}/meta`);
  } catch (err) {
    setStatus(`Failed to load dashboard: ${err.message}`);
    return;
  }
  setStatus("");
  buildFilters();
  // browsers restore form values on reload; query what the controls actually show
  fillPeriodDates();
  readFilterControls();
  if (!meta.items.length) setStatus("This dashboard is empty – add a KPI, chart or table using the buttons above.");
  for (const item of meta.items) renderWidget(item);
})();
