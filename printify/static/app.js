"use strict";

const PAPER_LABELS = {
  a3: "A3", a4: "A4", a5: "A5", letter: "Letter", legal: "Legal",
  tabloid: "Tabloid", statement: "Statement",
};

const $ = (id) => document.getElementById(id);
const form = $("form");
const fileInput = $("file");
const drop = $("drop");
const submit = $("submit");
const progress = $("progress");
const result = $("result");
let maxUploadMb = 50;
let selected = null;

function showResult(text, kind) {
  result.textContent = text;
  result.className = "result " + (kind || "");
}

function setFile(file) {
  if (!file) return;
  const isPdf = file.type === "application/pdf" || /\.pdf$/i.test(file.name);
  if (!isPdf) {
    showResult("Only PDF files are supported for now.", "err");
    return;
  }
  if (file.size > maxUploadMb * 1024 * 1024) {
    showResult(`File is too large (max ${maxUploadMb} MB).`, "err");
    return;
  }
  selected = file;
  $("drop-text").textContent = `${file.name} (${(file.size / 1024 / 1024).toFixed(1)} MB)`;
  drop.classList.add("has-file");
  submit.disabled = false;
  showResult("");
}

fileInput.addEventListener("change", () => setFile(fileInput.files[0]));
["dragenter", "dragover"].forEach((ev) =>
  drop.addEventListener(ev, (e) => { e.preventDefault(); drop.classList.add("over"); }));
["dragleave", "drop"].forEach((ev) =>
  drop.addEventListener(ev, (e) => { e.preventDefault(); drop.classList.remove("over"); }));
drop.addEventListener("drop", (e) => setFile(e.dataTransfer.files[0]));

form.addEventListener("submit", (e) => {
  e.preventDefault();
  if (!selected) return;

  const data = new FormData(form);
  data.set("file", selected, selected.name);

  const xhr = new XMLHttpRequest();
  xhr.open("POST", "/api/print");
  xhr.upload.onprogress = (ev) => {
    if (ev.lengthComputable) progress.value = (ev.loaded / ev.total) * 100;
  };
  xhr.onload = () => {
    let body = {};
    try { body = JSON.parse(xhr.responseText); } catch (_) { /* non-JSON error page */ }
    if (xhr.status === 200 && body.ok) {
      showResult(`✓ ${body.message} (${body.pages} page${body.pages === 1 ? "" : "s"})`, "ok");
      loadJobs();
    } else {
      showResult(body.error || `Printing failed (HTTP ${xhr.status}).`, "err");
    }
    done();
  };
  xhr.onerror = () => { showResult("Could not reach the print server.", "err"); done(); };

  submit.disabled = true;
  submit.textContent = "Sending…";
  progress.value = 0;
  progress.hidden = false;
  showResult("");
  xhr.send(data);
});

function done() {
  submit.disabled = !selected;
  submit.textContent = "Print";
  progress.hidden = true;
}

function applyCaps(caps) {
  // null = the driver didn't say, so keep the option visible.
  $("duplex-field").hidden = caps.duplex === false;
  if (caps.duplex === false) form.duplex.value = "off";
  $("color-field").hidden = caps.color === false;
  if (caps.color === false) form.color.value = "mono";

  const papers = caps.papers && caps.papers.length ? caps.papers : Object.keys(PAPER_LABELS);
  const paper = $("paper");
  const current = paper.value;
  paper.length = 1; // keep "Printer default"
  for (const key of papers) paper.add(new Option(PAPER_LABELS[key] || key, key));
  if (papers.includes(current)) paper.value = current;
}

async function loadPrinter() {
  const el = $("printer");
  try {
    const res = await fetch("/api/printer");
    const body = await res.json();
    if (!body.ok) throw new Error(body.error);
    maxUploadMb = body.max_upload_mb;
    const status = body.status.join(", ");
    el.textContent = `${body.name} · ${status}`;
    el.classList.toggle("bad", /offline|error|jam|out of|attention|door|not available/i.test(status));
    applyCaps(body.caps);
  } catch (err) {
    el.textContent = err.message || "Printer not available.";
    el.classList.add("bad");
  }
}

async function loadJobs() {
  const tbody = $("jobs").tBodies[0];
  try {
    const res = await fetch("/api/jobs");
    const body = await res.json();
    if (!body.ok) throw new Error(body.error);
    tbody.replaceChildren();
    if (!body.jobs.length) {
      const row = tbody.insertRow();
      const cell = row.insertCell();
      cell.colSpan = 3;
      cell.className = "muted";
      cell.textContent = "No jobs in the queue.";
      return;
    }
    for (const job of body.jobs) {
      const row = tbody.insertRow();
      row.insertCell().textContent = job.document;
      row.insertCell().textContent = job.status;
      row.insertCell().textContent = job.pages ? `${job.printed}/${job.pages}` : "–";
    }
  } catch (err) {
    tbody.innerHTML = "";
    const cell = tbody.insertRow().insertCell();
    cell.colSpan = 3;
    cell.className = "muted";
    cell.textContent = err.message || "Could not load the queue.";
  }
}

loadPrinter();
loadJobs();
setInterval(loadJobs, 4000);
setInterval(loadPrinter, 30000);
