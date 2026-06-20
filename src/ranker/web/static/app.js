"use strict";
const $ = (s) => document.querySelector(s);
const enc = encodeURIComponent;

let LIST = null;
let SCALE = 7;
let KUSER = false; // has the user manually set the tier count?
let CURRENT = null; // {left, right}
let LAST = null; // last state payload (for resume)
let SCREEN = "home";

async function api(path, opts) {
  const r = await fetch("/api" + path, opts);
  if (!r.ok) {
    let msg = r.statusText;
    try { msg = (await r.json()).detail || msg; } catch (e) {}
    throw new Error(msg);
  }
  return r.json();
}
const post = (path, body) =>
  api(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: body ? JSON.stringify(body) : undefined,
  });

function show(id) {
  document.querySelectorAll(".screen").forEach((s) => s.classList.add("hidden"));
  $("#" + id).classList.remove("hidden");
  SCREEN = id;
}

function imgSrc(image) {
  if (!image) return null;
  return /^https?:\/\//.test(image) ? image : "/images/" + image;
}

// -- home ---------------------------------------------------------------------

async function loadHome() {
  const lists = await api("/lists");
  const ul = $("#lists");
  ul.innerHTML = "";
  if (!lists.length) ul.innerHTML = '<li class="hint">No lists yet — create one.</li>';
  for (const l of lists) {
    const li = document.createElement("li");
    const span = document.createElement("span");
    span.innerHTML = `${l.name} <span class="hint">(${l.n_items} items)</span>`;
    const b = document.createElement("button");
    b.textContent = "Rank";
    b.onclick = () => openSession(l.name);
    li.append(span, b);
    ul.appendChild(li);
  }
  show("home");
}

// -- new list -----------------------------------------------------------------

async function createList() {
  $("#nl-error").textContent = "";
  const name = $("#nl-name").value.trim();
  const scale = parseInt($("#nl-scale").value, 10);
  const items = $("#nl-items").value
    .split("\n")
    .map((line) => line.trim())
    .filter(Boolean)
    .map((line) => {
      const [n, image, description] = line.split("|").map((x) => (x || "").trim());
      return { name: n, image: image || null, description: description || null };
    });
  try {
    await post("/lists", { name, scale, items });
    await loadHome();
  } catch (e) {
    $("#nl-error").textContent = e.message;
  }
}

// -- compare ------------------------------------------------------------------

function renderCard(el, item) {
  el.innerHTML = "";
  const src = imgSrc(item.image);
  if (src) {
    const im = document.createElement("img");
    im.src = src;
    im.alt = item.name;
    el.appendChild(im);
  }
  const n = document.createElement("div");
  n.className = "name";
  n.textContent = item.name;
  el.appendChild(n);
  if (item.description) {
    const d = document.createElement("div");
    d.className = "desc";
    d.textContent = item.description;
    el.appendChild(d);
  }
}

function buildButtons(scale) {
  const wrap = $("#buttons");
  wrap.innerHTML = "";
  const mid = (scale + 1) / 2;
  for (let i = 1; i <= scale; i++) {
    const b = document.createElement("button");
    b.textContent = i;
    if (i === mid) b.classList.add("mid");
    b.onclick = () => submit(i);
    wrap.appendChild(b);
  }
  $("#hk-max").textContent = scale;
}

function renderCompare(st) {
  SCALE = st.scale;
  CURRENT = st.pair;
  const p = st.progress;
  const frac = p.target ? Math.min(st.asked / p.target, 1) : 0;
  $("#bar").style.width = Math.round(frac * 100) + "%";
  $("#bar").classList.toggle("full", frac >= 1);
  let txt = `${st.asked} of ~${p.target} suggested · ${Math.round(p.confidence * 100)}% confident`;
  if (p.remaining_to_target > 0) txt += ` · ~${p.remaining_to_target} to suggested`;
  else txt += " · ✓ past suggested — finish anytime";
  if (p.unsettled_pairs) txt += ` · ${p.unsettled_pairs} near-ties`;
  $("#prog-text").textContent = txt;
  renderCard($("#card-left"), st.pair.left);
  renderCard($("#card-right"), st.pair.right);
  $("#lbl-left").textContent = st.pair.left.name;
  $("#lbl-right").textContent = st.pair.right.name;
  buildButtons(st.scale);
  show("compare");
}

function applyState(st) {
  LAST = st;
  if (!st.pair) return showResult(false); // nothing left to ask
  renderCompare(st);
}

async function openSession(name) {
  LIST = name;
  const st = await api("/session/" + enc(name));
  // Default tier count to floor(sqrt(n)); user can adjust with the stepper.
  KUSER = false;
  $("#tier-k").value = Math.max(1, Math.floor(Math.sqrt(st.n_items || 4)));
  applyState(st);
}

async function submit(answer) {
  if (!CURRENT) return;
  const st = await post("/session/" + enc(LIST) + "/answer", {
    left: CURRENT.left.name,
    right: CURRENT.right.name,
    answer,
  });
  applyState(st);
}

async function undo() {
  applyState(await post("/session/" + enc(LIST) + "/undo"));
}

// -- result -------------------------------------------------------------------

function tierParams() {
  const k = parseInt($("#tier-k").value, 10) || 1;
  return new URLSearchParams({ method: "kmeans", k }).toString();
}

function renderResult(data, doExport) {
  const tiersEl = $("#tiers");
  tiersEl.innerHTML = "";
  data.tiers.forEach((tier, i) => {
    const div = document.createElement("div");
    div.className = "tier";
    const h = document.createElement("h3");
    h.textContent = `Tier ${i + 1} (${tier.length})`;
    const ol = document.createElement("ol");
    ol.className = "tier-items";
    tier.forEach((entry) => {
      const li = document.createElement("li");
      const name = document.createElement("span");
      name.textContent = entry.item.name;
      const score = document.createElement("span");
      score.className = "score";
      score.textContent = entry.score.toFixed(2);
      li.append(name, score);
      ol.appendChild(li);
    });
    div.append(h, ol);
    tiersEl.appendChild(div);
  });
  const ratio = data.cycles.inconsistency_ratio;
  let note = `Intransitivity: ${Math.round(ratio * 100)}% of your preference strength is cyclic.`;
  if (data.cycles.cycles.length) {
    note += " Loop: " + data.cycles.cycles[0].items.join(" → ");
  }
  $("#cycles").textContent = note;
  if (doExport) $("#result-title").textContent = "Ranking (saved)";
}

async function showResult(doExport) {
  const q = tierParams();
  const data = doExport
    ? (await post("/session/" + enc(LIST) + "/finish?" + q)).result
    : await api("/session/" + enc(LIST) + "/result?" + q);
  if (!doExport) $("#result-title").textContent = "Ranking so far";
  renderResult(data, doExport);
  show("result");
}

// -- wiring -------------------------------------------------------------------

document.addEventListener("keydown", (e) => {
  if (SCREEN !== "compare") return;
  const n = parseInt(e.key, 10);
  if (!Number.isNaN(n) && n >= 1 && n <= SCALE) submit(n);
});

$("#show-new").onclick = () => show("newlist");
$("#nl-cancel").onclick = loadHome;
$("#nl-create").onclick = createList;
$("#undo").onclick = undo;
$("#finish").onclick = () => showResult(true);
$("#resume").onclick = () => (LAST && LAST.pair ? renderCompare(LAST) : openSession(LIST));
$("#home-from-compare").onclick = loadHome;
$("#home-from-result").onclick = loadHome;
$("#tier-k").oninput = () => {
  KUSER = true;
  showResult(false);
};

loadHome();
