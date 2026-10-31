"use strict";

pdfjsLib.GlobalWorkerOptions.workerSrc = "https://cdnjs.cloudflare.com/ajax/libs/pdf.js/3.11.174/pdf.worker.min.js";

const $ = (sel, root = document) => root.querySelector(sel);
const $$ = (sel, root = document) => [...root.querySelectorAll(sel)];

function h(tag, props = {}, ...kids) {
  const node = document.createElement(tag);
  for (const [k, v] of Object.entries(props)) {
    if (k === "class") node.className = v;
    else if (k.startsWith("on")) node.addEventListener(k.slice(2), v);
    else if (v === true) node.setAttribute(k, "");
    else if (v !== false && v != null) node.setAttribute(k, v);
  }
  node.append(...kids.flat().filter((x) => x != null));
  return node;
}

const ANSWERS = ["Yes", "No", "Cannot answer"];
const PUBLISHABLE = ["Yes", "No", "Cannot assess"];
const DOCX_NAMES = { assessment: "Detailed Assessment Report", confidential: "CONFIDENTIAL scoring", combined: "Assessment and CONFIDENTIAL scoring" };

const BANNERS = {
  word: "Read-only copy. This PDF was made from your Word file, so pages break as they do in Word. Nothing here can be edited; put your changes in the feedback panel.",
  libreoffice: "Read-only preview. This PDF was made from your Word file by LibreOffice, so page breaks may differ slightly from Word. Nothing here can be edited.",
  html: "Simplified preview. Page breaks and some formatting aren't shown. Nothing here can be edited.",
  pdf: "Read-only view of the PDF you uploaded. Nothing here can be edited; put your changes in the feedback panel.",
};

let cfg = null; // questions, score maxima, section names (from the server)
let S = null; // current session: { id, kind, filename, review, confirmed, active }
let pdf = null; // { doc, scale, pages: Map<number, {el, rendered}> }
let pdfHit = null; // last locate response, so highlights survive a relayout

// ---------------------------------------------------------------- home: upload + list

const drop = $("#drop");
const picker = $("#picker");
let list = [];
let pollTimer = null;

drop.addEventListener("click", () => !drop.classList.contains("busy") && picker.click());
drop.addEventListener("keydown", (e) => (e.key === "Enter" || e.key === " ") && (e.preventDefault(), drop.click()));
picker.addEventListener("change", () => picker.files.length && send(picker.files));
for (const t of ["dragenter", "dragover"]) drop.addEventListener(t, (e) => (e.preventDefault(), drop.classList.add("over")));
for (const t of ["dragleave", "drop"]) drop.addEventListener(t, (e) => (e.preventDefault(), drop.classList.remove("over")));
drop.addEventListener("drop", (e) => e.dataTransfer.files.length && !drop.classList.contains("busy") && send(e.dataTransfer.files));

function showError(msg) {
  const box = $("#error");
  box.textContent = msg;
  box.hidden = !msg;
}

async function send(files) {
  showError("");
  drop.classList.add("busy");
  $("#dropIdle").hidden = true;
  $("#dropBusy").hidden = false;
  try {
    const body = new FormData();
    [...files].forEach((f) => body.append("files", f));
    const res = await fetch("/api/jobs", { method: "POST", body });
    if (!res.ok) throw new Error("The upload failed. Check your connection and try again.");
    const { rejected } = await res.json();
    if (rejected.length) showError(rejected.map((r) => `${r.filename}: ${r.reason}`).join("\n"));
    await refresh();
  } catch (err) {
    showError(err.message);
  } finally {
    drop.classList.remove("busy");
    $("#dropIdle").hidden = false;
    $("#dropBusy").hidden = true;
    picker.value = "";
  }
}

const api = async (url, opts) => {
  const res = await fetch(url, opts);
  if (!res.ok) throw new Error((await res.json().catch(() => ({}))).detail || "Something went wrong.");
  return res.json();
};

async function refresh() {
  clearTimeout(pollTimer);
  list = await api("/api/jobs");
  renderLedger();
  if (!S && list.some((j) => j.status === "queued" || j.status === "working")) pollTimer = setTimeout(refresh, 2000);
}

const STATUS = {
  queued: ["Waiting", ""], working: ["Grading", "working"], ready: ["Ready to review", "ready"],
  confirmed: ["Confirmed", "done"], error: ["Failed", "failed"],
};

function renderLedger() {
  $("#pitch").hidden = list.length > 0;
  $("#ledger").hidden = list.length === 0;
  $("#intake").classList.toggle("has-jobs", list.length > 0);
  const counts = { ready: 0, active: 0, done: 0 };
  const rows = list.map((j) => {
    const key = j.status === "ready" && j.confirmed ? "confirmed" : j.status;
    if (key === "confirmed") counts.done++;
    else if (key === "ready") counts.ready++;
    else if (key === "queued" || key === "working") counts.active++;
    const [label, cls] = STATUS[key];
    const open = j.status === "ready";
    const name = h("span", { class: "row-name" }, j.candidate || j.filename.replace(/\.[^.]+$/, ""));
    const sub = h("span", { class: "row-sub" }, j.title || (j.candidate ? j.filename : j.error || j.filename));
    const main = h(open ? "a" : "div", { class: "row-main", href: open ? `#/job/${j.id}` : null }, name, sub);
    const actions = h("span", { class: "row-actions" });
    if (j.status === "error") actions.append(h("button", { class: "link", type: "button", onclick: () => api(`/api/jobs/${j.id}/retry`, { method: "POST" }).then(refresh) }, "Retry"));
    actions.append(h("button", { class: "link quiet", type: "button", "aria-label": `Remove ${j.filename}`, onclick: () => confirm(`Remove ${j.filename}? Its grade and edits will be deleted.`) && api(`/api/jobs/${j.id}`, { method: "DELETE" }).then(refresh) }, "Remove"));
    return h("li", { class: `row ${cls}` },
      h("span", { class: "dot", "aria-hidden": "true" }), main,
      h("span", { class: "row-score" }, j.total == null ? "" : `${j.total}`, j.total == null ? null : h("small", {}, "/60")),
      h("span", { class: "chip" }, label), actions);
  });
  $("#ledgerRows").replaceChildren(...rows);
  $("#ledgerCount").textContent = [
    counts.active && `${counts.active} grading`, counts.ready && `${counts.ready} to review`, counts.done && `${counts.done} confirmed`,
  ].filter(Boolean).join(" · ");
}

// ---------------------------------------------------------------- routing + saving

const intake = $("#intake");
$("#backBtn").addEventListener("click", () => (location.hash = ""));
window.addEventListener("hashchange", route);

async function route() {
  await flushSave();
  const m = location.hash.match(/^#\/job\/(\w+)/);
  if (!m) return showHome();
  try {
    const job = await api(`/api/jobs/${m[1]}`);
    if (job.status !== "ready") return (location.hash = "");
    S = { id: job.id, kind: job.renderer === "html" ? "html" : "pdf", renderer: job.renderer, filename: job.filename,
      review: normalise(job.review), assessor: job.assessor, confirmed: null, active: null };
    S.confirmed = job.confirmed ? sig() : null;
    intake.hidden = true;
    await openReview();
  } catch (err) {
    location.hash = "";
  }
}

function showHome() {
  S = pdf = pdfHit = null;
  $("#review").hidden = true;
  intake.hidden = false;
  for (const id of ["backBtn", "fileName", "saveState"]) $("#" + id).hidden = true;
  $("#pdfPages").replaceChildren();
  $("#htmlHost").shadowRoot?.replaceChildren();
  clearInk();
  refresh();
}

let saveTimer = null;
let dirty = false;

function scheduleSave() {
  dirty = true;
  $("#saveState").textContent = "Unsaved changes";
  clearTimeout(saveTimer);
  saveTimer = setTimeout(flushSave, 700);
}

async function flushSave() {
  clearTimeout(saveTimer);
  if (!dirty || !S) return;
  dirty = false;
  const label = $("#saveState");
  label.textContent = "Saving…";
  try {
    await api(`/api/jobs/${S.id}`, { method: "PUT", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ review: S.review, assessor: S.assessor, confirmed: S.confirmed === sig() }), keepalive: true });
    label.textContent = "All changes saved";
  } catch {
    dirty = true;
    label.textContent = "Couldn't save. Retrying…";
    saveTimer = setTimeout(flushSave, 3000);
  }
}

// Fill gaps so every question, section and criterion has a row to edit.
function normalise(r) {
  const by = (list, key) => new Map(list.map((x) => [String(x[key]).trim().toLowerCase(), x]));
  const sections = by(r.section_comments, "section");
  const scores = by(r.scores, "criterion");
  const answers = new Map(r.checklist.map((x) => [x.number, x]));
  r.section_comments = cfg.sections.map((s) => sections.get(s.toLowerCase()) ?? { section: s, comment: "", quote: "" });
  r.scores = Object.keys(cfg.score_maxima).map((c) => {
    const row = scores.get(c.toLowerCase()) ?? { criterion: c, score: 0, justification: "", quote: "" };
    row.criterion = c;
    return row;
  });
  r.checklist = cfg.checklist.map((_, i) => answers.get(i + 1) ?? { number: i + 1, answer: "Cannot answer", comment: "", quote: "" });
  return r;
}

// ---------------------------------------------------------------- review screen

async function openReview() {
  $("#review").hidden = false;
  for (const id of ["backBtn", "fileName", "saveState"]) $("#" + id).hidden = false;
  $("#saveState").textContent = "All changes saved";
  $("#fileName").textContent = S.filename;
  $("#docBanner").textContent = BANNERS[S.renderer];
  $$("[data-meta]").forEach((input) => {
    input.value = S.review[input.dataset.meta];
    input.oninput = () => ((S.review[input.dataset.meta] = input.value), changed());
  });
  buildAssessment();
  buildConfidential();
  selectTab("assessment");
  renderDock();
  await (S.kind === "pdf" ? loadPdf() : loadHtml());
}

function bind(input, obj, key, after) {
  input.addEventListener("input", () => {
    obj[key] = input.value;
    if (input.tagName === "TEXTAREA") fit(input);
    changed();
    after?.();
  });
}

function fit(t) {
  t.style.height = "auto";
  t.style.height = t.scrollHeight + 2 + "px";
}

function area(obj, key, label, placeholder = "") {
  const t = h("textarea", { rows: 1, "aria-label": label, placeholder });
  t.value = obj[key];
  bind(t, obj, key);
  return t;
}

function seg(name, options, obj, key) {
  return h("div", { class: "seg", role: "radiogroup" },
    options.map((o) => {
      const input = h("input", { type: "radio", name, value: o, checked: obj[key] === o });
      input.addEventListener("change", () => ((obj[key] = o), changed()));
      return h("label", {}, input, h("span", {}, o));
    }));
}

function locateBtn(row, item) {
  const btn = h("button", {
    class: "locate", type: "button", disabled: !row.quote,
    title: row.quote || "The AI gave no supporting passage for this.",
    onclick: () => locate(row, item, btn),
  }, row.quote ? "Show in document" : "No passage cited");
  return btn;
}

function buildAssessment() {
  const pane = $("#pane-assessment");
  pane.replaceChildren(h("h2", {}, "Checklist"));
  S.review.checklist.forEach((row, i) => {
    const item = h("div", { class: "item" });
    const comment = area(row, "comment", `Comment on item ${row.number}`, "Comment");
    item.append(
      h("div", { class: "item-head" }, h("div", { class: "q" }, h("span", {}, String(row.number).padStart(2, "0")), h("b", {}, cfg.checklist[i]))),
      seg(`ans${row.number}`, ANSWERS, row, "answer"), comment, locateBtn(row, item));
    pane.append(item);
  });

  pane.append(h("h2", {}, "Comments by section"));
  S.review.section_comments.forEach((row) => {
    const item = h("div", { class: "item" });
    item.append(h("div", { class: "item-head" }, h("b", {}, row.section)), area(row, "comment", `${row.section} comment`, "No comment"), locateBtn(row, item));
    pane.append(item);
  });

  pane.append(h("h2", {}, "Verdict"));
  const general = h("div", { class: "item" },
    h("div", { class: "item-head" }, h("b", {}, "Is the work publishable?")),
    seg("publishable", PUBLISHABLE, S.review, "publishable"));
  const overall = h("div", { class: "item" },
    h("div", { class: "item-head" }, h("b", {}, "General comments on the work")),
    area(S.review, "general_comments", "General comments", "No comment"));
  pane.append(general, overall);
}

function buildConfidential() {
  const pane = $("#pane-confidential");
  pane.replaceChildren(h("p", { class: "stamp" }, "Confidential · not for the student"), h("h2", {}, "Scores"));
  S.review.scores.forEach((row) => {
    const max = cfg.score_maxima[row.criterion];
    const num = h("input", { type: "number", min: 0, max, step: 1, "aria-label": `${row.criterion} score out of ${max}` });
    num.value = row.score;
    num.addEventListener("input", () => {
      row.score = Math.max(0, Math.min(max, Math.round(Number(num.value) || 0)));
      changed();
    });
    num.addEventListener("change", () => (num.value = row.score));
    const item = h("div", { class: "item" });
    item.append(
      h("div", { class: "item-head" }, h("b", {}, row.criterion), h("span", { class: "max" }, `out of ${max}`)),
      h("div", { class: "score-box" }, num),
      area(row, "justification", `${row.criterion} justification`, "Why this score"),
      locateBtn(row, item));
    pane.append(item);
  });

  pane.append(h("h2", {}, "Assessor, printed under the table"));
  for (const [key, label] of [["name", "Name of assessor"], ["email", "Email address"], ["phone", "Telephone"]]) {
    const input = h("input", { class: "field", "aria-label": label, placeholder: label });
    input.value = S.assessor[key];
    bind(input, S.assessor, key);
    pane.append(h("div", { class: "item" }, h("div", { class: "item-head" }, h("b", {}, label)), input));
  }
}

function selectTab(name) {
  for (const id of ["assessment", "confidential"]) {
    $(`#tab-${id}`).setAttribute("aria-selected", id === name);
    $(`#pane-${id}`).hidden = id !== name;
  }
  $$("textarea", $(`#pane-${name}`)).forEach(fit);
  updateInk();
}
$$(".tabs button").forEach((b) => b.addEventListener("click", () => selectTab(b.id.replace("tab-", ""))));
$$(".panes").forEach((p) => p.addEventListener("scroll", updateInk));

// ---------------------------------------------------------------- confirm + download

const sig = () => JSON.stringify({ review: S.review, assessor: S.assessor });
const total = () => S.review.scores.reduce((n, s) => n + s.score, 0);

function changed() {
  $("#total").textContent = total();
  renderDock();
  scheduleSave();
}

function renderDock() {
  $("#total").textContent = total();
  const box = $("#dockActions");
  if (S.confirmed === sig()) {
    box.replaceChildren(
      h("span", { class: "hint" }, "Confirmed. Editing again locks the downloads."),
      downloadBtn("assessment", "Assessment report", "btn"),
      downloadBtn("confidential", "Confidential scoring", "btn red"),
      downloadBtn("combined", "Both in one file", "btn dark", "Contains the confidential page. Do not send to the student."));
    return;
  }
  const edited = S.confirmed !== null;
  box.replaceChildren(
    edited ? h("span", { class: "hint" }, h("b", {}, "Edited."), " Confirm again to download.")
      : h("span", { class: "hint" }, "Review everything, then confirm to unlock downloads."),
    h("button", { class: "btn primary", type: "button", onclick: () => ((S.confirmed = sig()), renderDock(), scheduleSave(), flushSave()) }, "Confirm review"));
}

function downloadBtn(kind, label, cls, title = "") {
  const btn = h("button", { class: cls, type: "button", title }, `↓ ${label}`);
  btn.addEventListener("click", async () => {
    btn.disabled = true;
    try {
      const res = await fetch(`/api/report/${kind}`, { method: "POST", headers: { "Content-Type": "application/json" }, body: sig() });
      if (!res.ok) throw new Error("The report could not be built.");
      const url = URL.createObjectURL(await res.blob());
      const stem = S.filename.replace(/\.[^.]+$/, "");
      const a = h("a", { href: url, download: `${stem} - ${DOCX_NAMES[kind]}.docx` });
      document.body.append(a);
      a.click();
      a.remove();
      setTimeout(() => URL.revokeObjectURL(url), 5000);
    } catch (err) {
      note(err.message);
    } finally {
      btn.disabled = false;
    }
  });
  return btn;
}

// ---------------------------------------------------------------- document: PDF

async function loadPdf() {
  $("#htmlHost").hidden = true;
  $("#pdfPages").hidden = false;
  pdf = { doc: await pdfjsLib.getDocument(`/api/file/${S.id}`).promise, pages: new Map(), observer: null };
  await layoutPdf();
}

async function layoutPdf() {
  const host = $("#pdfPages");
  const scroller = $("#docScroll");
  const first = await pdf.doc.getPage(1);
  const natural = first.getViewport({ scale: 1 });
  const width = Math.min(scroller.clientWidth - 40, 920);
  const ratio = natural.height / natural.width;
  pdf.width = width;
  pdf.observer?.disconnect();
  pdf.pages.clear();
  host.replaceChildren();
  pdf.observer = new IntersectionObserver((entries) => {
    for (const e of entries) if (e.isIntersecting) renderPage(Number(e.target.dataset.n));
  }, { root: scroller, rootMargin: "800px 0px" });
  for (let n = 1; n <= pdf.doc.numPages; n++) {
    const el = h("div", { class: "pdf-page", "data-n": n, style: `width:${width}px;height:${width * ratio}px` });
    pdf.pages.set(n, { el, task: null });
    host.append(el);
    pdf.observer.observe(el);
  }
}

function renderPage(n) {
  const entry = pdf.pages.get(n);
  if (!entry) return Promise.resolve();
  entry.task ??= (async () => {
    const page = await pdf.doc.getPage(n);
    const scale = pdf.width / page.getViewport({ scale: 1 }).width;
    const css = page.getViewport({ scale });
    const dpr = Math.min(window.devicePixelRatio || 1, 2);
    const canvas = h("canvas", { "aria-label": `Page ${n}` });
    canvas.width = css.width * dpr;
    canvas.height = css.height * dpr;
    await page.render({ canvasContext: canvas.getContext("2d"), viewport: page.getViewport({ scale: scale * dpr }) }).promise;
    entry.el.style.height = css.height + "px";
    entry.el.prepend(canvas);
    entry.el.append(h("span", { class: "pno" }, `p. ${n}`));
  })();
  return entry.task;
}

function drawPdfHighlight(scroll) {
  $$(".hl-box").forEach((b) => b.remove());
  if (!pdfHit?.page) return [];
  const entry = pdf.pages.get(pdfHit.page);
  const { width: W, height: H } = pdfHit;
  const boxes = pdfHit.rects.map(([x0, y0, x1, y1]) =>
    h("div", { class: "hl-box", style: `left:${(x0 / W) * 100}%;top:${(y0 / H) * 100}%;width:${((x1 - x0) / W) * 100}%;height:${((y1 - y0) / H) * 100}%` }));
  entry.el.append(...boxes);
  if (scroll) scrollTo(boxes[0]);
  return boxes;
}

function scrollTo(target) {
  const scroller = $("#docScroll");
  const delta = target.getBoundingClientRect().top - scroller.getBoundingClientRect().top - scroller.clientHeight * 0.3;
  scroller.scrollBy({ top: delta, behavior: "smooth" });
}

// ---------------------------------------------------------------- document: DOC / DOCX

const PAGE_CSS = `:host{display:block}.page{padding:56px 64px;font:16px/1.55 "Times New Roman",Times,serif;color:#111;overflow-wrap:anywhere}
table{border-collapse:collapse;margin:8px 0}td,th{border:1px solid #bbb;padding:3px 6px;vertical-align:top}img{max-width:100%;height:auto}
mark.hl{background:#ffe14d;outline:1.5px solid #d4a900;border-radius:2px;color:inherit}`;

// The converted HTML is untrusted: drop anything that can run or phone home before it touches the page.
function sanitise(html) {
  const doc = new DOMParser().parseFromString(html, "text/html");
  doc.querySelectorAll("script,iframe,object,embed,link,meta,base,form").forEach((n) => n.remove());
  doc.querySelectorAll("style").forEach((s) => (s.textContent = s.textContent.replace(/@import[^;]*;?/gi, "").replace(/url\([^)]*\)/gi, "none")));
  doc.querySelectorAll("*").forEach((n) => {
    for (const a of [...n.attributes]) {
      const v = a.value.trim().toLowerCase();
      const linkAttr = a.name === "href" || a.name === "src";
      if (a.name.startsWith("on") || (linkAttr && !(v.startsWith("data:image/") || v.startsWith("#") || (a.name === "href" && v.startsWith("http")))))
        n.removeAttribute(a.name);
      if (a.name === "style") n.setAttribute("style", a.value.replace(/url\([^)]*\)/gi, "none"));
    }
    if (n.tagName === "A") n.setAttribute("target", "_blank"), n.setAttribute("rel", "noopener noreferrer");
  });
  return [...doc.head.querySelectorAll("style")].map((s) => s.outerHTML).join("") + `<div class="page">${doc.body.innerHTML}</div>`;
}

async function loadHtml() {
  $("#pdfPages").hidden = true;
  const host = $("#htmlHost");
  host.hidden = false;
  const root = host.shadowRoot ?? host.attachShadow({ mode: "open" });
  const res = await fetch(`/api/html/${S.id}`);
  root.innerHTML = `<style>${PAGE_CSS}</style>` + sanitise(await res.text());
}

const fold = (s) => s.replace(/[‘’]/g, "'").replace(/[“”]/g, '"').replace(/[–—]/g, "-").toLowerCase();

// Collapse whitespace like the quote is collapsed, remembering where each character came from.
function textIndex(root) {
  const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT, {
    acceptNode: (n) => (n.parentElement.closest("style") ? NodeFilter.FILTER_REJECT : NodeFilter.FILTER_ACCEPT),
  });
  let text = "";
  const from = [];
  for (let node; (node = walker.nextNode()); ) {
    const raw = node.nodeValue;
    for (let i = 0; i < raw.length; i++) {
      const c = /\s/.test(raw[i]) ? " " : fold(raw[i]);
      if (c === " " && (text === "" || text.endsWith(" "))) continue;
      text += c;
      from.push([node, i]);
    }
  }
  return { text, from };
}

function highlightHtml(quote) {
  const root = $("#htmlHost").shadowRoot;
  root.querySelectorAll("mark.hl").forEach((m) => m.replaceWith(...m.childNodes));
  root.normalize();
  const { text, from } = textIndex(root);
  const words = fold(quote).split(/\s+/).filter(Boolean);
  for (const count of [12, 6, 4]) {
    const needle = words.slice(0, count).join(" ");
    const start = needle ? text.indexOf(needle) : -1;
    if (start < 0) continue;
    const spans = new Map(); // text node -> [first offset, last offset + 1]
    for (let k = start; k < start + needle.length; k++) {
      const [node, off] = from[k];
      const s = spans.get(node);
      spans.set(node, s ? [s[0], off + 1] : [off, off + 1]);
    }
    return [...spans].map(([node, [a, b]]) => {
      const range = document.createRange();
      range.setStart(node, a);
      range.setEnd(node, b);
      const mark = h("mark", { class: "hl" });
      range.surroundContents(mark);
      return mark;
    });
  }
  return [];
}

// ---------------------------------------------------------------- cross-reference + connector

async function locate(row, item, btn) {
  $$(".item.active").forEach((i) => i.classList.remove("active"));
  item.classList.add("active");
  S.active = { btn, target: null };
  let target = null;
  if (S.kind === "pdf") {
    pdfHit = await (await fetch(`/api/locate/${S.id}?q=${encodeURIComponent(row.quote)}`)).json();
    if (pdfHit.page) {
      await renderPage(pdfHit.page);
      target = drawPdfHighlight(true)[0];
    }
  } else {
    target = highlightHtml(row.quote)[0];
    if (target) scrollTo(target);
  }
  if (!target) {
    S.active = null;
    clearInk();
    return note("Couldn't find that passage. The AI may have paraphrased it.");
  }
  S.active.target = target;
  const ink = $("#ink");
  ink.classList.add("draw");
  updateInk();
  setTimeout(() => ink.classList.remove("draw"), 700);
}

function clearInk() {
  $("#ink").classList.remove("on");
}

function updateInk() {
  const ink = $("#ink");
  const a = S?.active;
  if (!a?.target?.isConnected || !a.btn.offsetParent || window.innerWidth <= 900) return clearInk();
  const clamp = (v, lo, hi) => Math.max(lo, Math.min(hi, v));
  const doc = $("#docScroll").getBoundingClientRect();
  const panes = $(".panes").getBoundingClientRect();
  const from = a.btn.getBoundingClientRect();
  const to = a.target.getBoundingClientRect();
  const sx = from.left - 6;
  const sy = clamp(from.top + from.height / 2, panes.top + 8, panes.bottom - 8);
  const ex = clamp(to.right + 6, doc.left + 8, doc.right - 24);
  const ey = clamp(to.top + to.height / 2, doc.top + 8, doc.bottom - 8);
  const dx = Math.max(60, (sx - ex) * 0.5);
  const path = $("#inkPath");
  path.setAttribute("d", `M${sx} ${sy} C${sx - dx} ${sy},${ex + dx} ${ey},${ex} ${ey}`);
  path.style.setProperty("--len", path.getTotalLength());
  const dot = $("#inkDot");
  dot.setAttribute("cx", ex);
  dot.setAttribute("cy", ey);
  ink.classList.add("on");
}

$("#docScroll").addEventListener("scroll", updateInk);
document.addEventListener("keydown", (e) => {
  if (e.key !== "Escape" || !S?.active) return;
  S.active = null;
  pdfHit = null;
  $$(".hl-box").forEach((b) => b.remove());
  $("#htmlHost").shadowRoot?.querySelectorAll("mark.hl").forEach((m) => m.replaceWith(...m.childNodes));
  $$(".item.active").forEach((i) => i.classList.remove("active"));
  clearInk();
});

let noteTimer;
function note(msg) {
  const el = $("#docNote");
  el.textContent = msg;
  el.hidden = false;
  clearTimeout(noteTimer);
  noteTimer = setTimeout(() => (el.hidden = true), 4000);
}

// ---------------------------------------------------------------- layout: splitter + resize

const review = $("#review");
const splitter = $("#splitter");
let relayoutTimer;

function settle() {
  $$("textarea", $(".pane:not([hidden])")).forEach(fit);
  clearTimeout(relayoutTimer);
  relayoutTimer = setTimeout(async () => {
    if (pdf && S?.kind === "pdf" && Math.abs(Math.min($("#docScroll").clientWidth - 40, 920) - pdf.width) > 4) {
      const ratio = $("#docScroll").scrollTop / Math.max(1, $("#docScroll").scrollHeight);
      await layoutPdf();
      $("#docScroll").scrollTop = ratio * $("#docScroll").scrollHeight;
      if (pdfHit?.page) {
        await renderPage(pdfHit.page);
        const boxes = drawPdfHighlight(false);
        if (S.active) S.active.target = boxes[0];
      }
    }
    updateInk();
  }, 200);
}

function setWidth(px) {
  const max = window.innerWidth - 320;
  review.style.setProperty("--fb", `${Math.max(380, Math.min(max, px))}px`);
  settle();
}

splitter.addEventListener("pointerdown", (e) => {
  splitter.setPointerCapture(e.pointerId);
  const move = (ev) => setWidth(window.innerWidth - ev.clientX - 4);
  const stop = () => (splitter.removeEventListener("pointermove", move), splitter.removeEventListener("pointerup", stop));
  splitter.addEventListener("pointermove", move);
  splitter.addEventListener("pointerup", stop);
});
splitter.addEventListener("keydown", (e) => {
  const now = $(".feedback").getBoundingClientRect().width;
  if (e.key === "ArrowLeft") setWidth(now + 24);
  if (e.key === "ArrowRight") setWidth(now - 24);
});
window.addEventListener("resize", settle);

// ---------------------------------------------------------------- start

(async () => {
  cfg = await api("/api/config");
  route();
})();
