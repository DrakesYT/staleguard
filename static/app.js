// StaleGuard frontend: vanilla JS, no build step.
const $ = (s) => document.querySelector(s);
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const COLORS = { current: "var(--current)", aging: "var(--aging)", disputed: "var(--disputed)", outdated: "var(--outdated)", unverified: "var(--unverified)" };
const LABEL = { current: "Current", aging: "Aging", disputed: "Disputed", outdated: "Outdated", unverified: "Unverified" };
const VERDICTS = ["current", "aging", "disputed", "outdated", "unverified"];

const SAMPLE = `Here's a quick overview. OpenAI's flagship model is GPT-4, and ChatGPT Plus costs $20 per month. The newest stable Python release is Python 3.11. Twitter's CEO is Parag Agrawal. The EU AI Act is still being negotiated and has not been adopted. Stripe was last valued at $95 billion. React's latest major version is React 18.`;

async function api(path, opts = {}) {
  const r = await fetch(path, { headers: { "Content-Type": "application/json" }, ...opts });
  const body = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(body.detail || `HTTP ${r.status}`);
  return body;
}
const loading = (msg) => `<div class="loading"><span class="spinner"></span>${esc(msg)}</div>`;
const errorBox = (e) => `<div class="error">${esc(e.message || e)}</div>`;
const shortModel = (m) => String(m || "").replace(/^([^/]+)\/(?:openai\/|qwen\/)?/, "$1/");

// ---------- tabs ----------
document.querySelectorAll(".tab").forEach((t) =>
  t.addEventListener("click", () => {
    document.querySelectorAll(".tab").forEach((x) => x.classList.toggle("active", x === t));
    document.querySelectorAll(".panel").forEach((p) => p.classList.toggle("hidden", p.id !== `tab-${t.dataset.tab}`));
    if (t.dataset.tab === "brief") loadBriefList();
  })
);

// ---------- health ----------
(async () => {
  try {
    const h = await api("/api/health");
    const ok = h.bifrost.reachable && h.tavily_key_set;
    const chain = [h.models.fast, ...h.models.fallbacks.filter((m) => m !== h.models.fast)].map(shortModel);
    $("#health").innerHTML =
      `<span class="dot" style="background:${ok ? "var(--current)" : "var(--outdated)"}"></span>` +
      (h.mock ? "Offline demo mode" : `Bifrost ${h.bifrost.reachable ? "connected" : "unreachable"} · Tavily ${h.tavily_key_set ? "ready" : "key missing"}`) +
      (h.virtual_key ? `<span id="health-budget" title="Every model call is authorised by this Bifrost virtual key"></span>` : "") +
      `<br><span title="Bifrost tries these in order">${esc(chain.join(" → "))}</span>`;
    if (h.virtual_key) refreshBudget();
  } catch { $("#health").textContent = "API offline"; }
})();

// ---------- shared renderers ----------
function gauge(score) {
  const color = score >= 70 ? "var(--current)" : score >= 45 ? "var(--aging)" : "var(--outdated)";
  return `<div class="gauge" style="background:conic-gradient(${color} ${score * 3.6}deg, var(--line) 0)"><span>${score}</span></div>`;
}
const pill = (v, n) => `<span class="pill v-${v}">${LABEL[v]}${n !== undefined ? ` · ${n}` : ""}</span>`;

function usageBlock(u, simulated) {
  const served = Object.entries(u.served_by).map(([k, v]) => `${esc(shortModel(k))} ×${v}`).join(", ") || "-";
  const calls = u.calls || [];
  const fb = calls.filter((c) => c.fallback);
  const banner = fb.length
    ? `<div class="fallback-banner">⤳ <b>Bifrost fallback × ${fb.length}</b>: ${esc(shortModel(fb[0].requested))} failed${simulated ? " (simulated outage)" : ""},
       served by ${esc([...new Set(fb.map((c) => shortModel(c.served)))].join(", "))}. The check carried on without errors.</div>` : "";
  const rows = calls.map((c) => `<tr class="${c.fallback ? "fb" : ""}"><td>${esc(c.task)}</td>
      <td>${esc(shortModel(c.requested))}</td><td>${c.fallback ? "⤳ " : ""}${esc(shortModel(c.served))}</td>
      <td>${c.fallback ? '<span class="tag">fallback</span>' : "primary"}</td><td class="num">${c.tokens.toLocaleString()}</td><td class="num">${(c.ms / 1000).toFixed(1)}s</td></tr>`).join("");
  return `<div class="card usage-card">${banner}<div class="usage">
    <span>LLM calls <b>${u.llm_calls}</b></span>
    <span>Tokens <b>${(u.prompt_tokens + u.completion_tokens).toLocaleString()}</b></span>
    <span>Est. cost <b>$${u.cost_usd.toFixed(4)}</b></span>
    <span>Fallbacks <b class="${u.fallbacks_used ? "warn" : ""}">${u.fallbacks_used}</b></span>
    <span>Tavily searches <b>${u.tavily_searches}</b> (+${u.cache_hits} cached)</span>
    <span>Served by <b>${served}</b></span></div>
    <div class="budget-slot"></div>
    ${calls.length ? `<details><summary>Bifrost routing log · ${calls.length} calls</summary>
      <table class="routing"><thead><tr><th>Task</th><th>Requested</th><th>Served by</th><th>Route</th><th class="num">Tokens</th><th class="num">Time</th></tr></thead>
      <tbody>${rows}</tbody></table></details>` : ""}</div>`;
}

// Spend of the app's Bifrost virtual key, read live from Bifrost's governance API.
const money = (x) => "$" + (x < 0.01 ? x.toFixed(4) : x.toFixed(2));
async function refreshBudget() {
  let b;
  try { b = await api("/api/budget"); } catch { return; }
  if (!b.available) return;
  const { used, limit, reset } = b.budget;
  const pct = limit ? Math.min(100, (used / limit) * 100) : 0;
  const [req, reqMax] = b.rate_limit.requests;
  const period = reset === "1d" ? "today" : `per ${reset}`;
  const html = `<div class="budget"><span>Bifrost virtual key <b>${esc(b.virtual_key)}</b> · spent ${period}
      <b>${money(used)}</b> of ${money(limit)} budget${reqMax ? ` · ${req}/${reqMax} requests this hour` : ""}</span>
    <div class="bar"><i style="width:${Math.max(pct, 0.8)}%;background:${pct > 85 ? "var(--outdated)" : "var(--current)"}"></i></div></div>`;
  document.querySelectorAll(".budget-slot").forEach((el) => (el.innerHTML = html));
  const hb = $("#health-budget");
  if (hb) hb.textContent = ` · budget ${money(used)} / ${money(limit)} ${period}`;
}

function evidenceRows(evidence) {
  return evidence.map((e) => `
    <div class="ev"><span class="st ${e.stance}">${e.stance}</span>
      <span><a href="${esc(e.url)}" target="_blank" rel="noopener">${esc(e.title || e.domain)}</a>
        <span class="meta">${esc(e.domain)}${e.note ? " · " + esc(e.note) : ""}</span></span>
      <span class="date">${esc(e.published || "undated")}</span></div>`).join("");
}

function claimCard(c, r) {
  if (!r) {
    return `<div class="claim pending" id="card-${esc(c.id)}">
      <div class="claim-head"><div class="claim-text">${esc(c.text)}</div><span class="pill v-unverified"><span class="spinner sm"></span>Checking</span></div>
      <div class="meta">${esc(c.category.replace("_", " "))} · searching the live web…</div></div>`;
  }
  const justArrived = V && !V.report && V.lastId === c.id;   // animate only the newest result
  return `<div class="claim ${r.verdict}${justArrived ? " arrived" : ""}" id="card-${esc(c.id)}">
    <div class="claim-head"><div class="claim-text">${esc(c.text)}</div>${pill(r.verdict)}</div>
    <div class="meta">${esc(c.category.replace("_", " "))}${c.value ? " · claimed: " + esc(c.value) : ""} · freshness ${r.freshness}/100</div>
    ${r.current_value ? `<div class="now">Live sources now say: <b>${esc(r.current_value)}</b></div>` : ""}
    ${r.error ? `<div class="meta">Check failed: ${esc(r.error)}</div>` : ""}
    <div class="bar"><i style="width:${r.freshness}%;background:${COLORS[r.verdict]}"></i></div>
    <details><summary>Why · ${r.evidence.length} sources</summary>
      <ul class="reasons">${r.reasons.map((x) => `<li>${esc(x)}</li>`).join("")}</ul>${evidenceRows(r.evidence)}</details>
  </div>`;
}

// ---------- verify: streaming ----------
$("#sample").addEventListener("click", () => { $("#answer").value = SAMPLE; $("#from-note").innerHTML = ""; });
$("#answer").addEventListener("input", () => ($("#from-note").innerHTML = ""));

let V = null;   // state of the current check: { text, claims, results: {id: ClaimResult}, phase, report }

$("#verify-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const text = $("#answer").value.trim();
  if (text.length < 20) return;
  const btn = $("#verify-btn");
  btn.disabled = true;
  V = { text, claims: null, results: {}, phase: "extract", report: null, simulated: $("#outage").checked };
  renderVerify();
  try {
    await streamVerify({ text, simulate_outage: V.simulated });
  } catch (err) {
    $("#verify-out").innerHTML = errorBox(err);
  }
  btn.disabled = false;
});

// POST + text/event-stream, parsed by hand (EventSource only does GET).
async function streamVerify(body) {
  const r = await fetch("/api/verify/stream", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
  if (!r.ok) { const b = await r.json().catch(() => ({})); throw new Error(b.detail ? JSON.stringify(b.detail) : `HTTP ${r.status}`); }
  const reader = r.body.getReader();
  const dec = new TextDecoder();
  let buf = "";
  for (;;) {
    const { value, done } = await reader.read();
    if (done) break;
    buf += dec.decode(value, { stream: true });
    let i;
    while ((i = buf.indexOf("\n\n")) >= 0) {
      const block = buf.slice(0, i); buf = buf.slice(i + 2);
      const ev = /^event: (.*)$/m.exec(block)?.[1];
      const data = /^data: (.*)$/m.exec(block)?.[1];
      if (ev && data) onEvent(ev, JSON.parse(data));
    }
  }
  if (V.phase !== "done") throw new Error("The connection closed before the check finished.");
}

function onEvent(ev, data) {
  if (ev === "claims") { V.claims = data.claims; V.phase = "check"; }
  else if (ev === "result") { V.results[data.claim.id] = data; V.lastId = data.claim.id; }
  else if (ev === "refresh") { V.phase = "refresh"; }
  else if (ev === "done") { V.report = data; V.phase = "done"; }
  else if (ev === "error") { throw new Error(data.detail); }
  renderVerify();
}

function annotated(text, claims, results) {
  // Non-overlapping spans, in text order; a claim the model couldn't quote just isn't highlighted.
  const spans = claims.filter((c) => c.span).sort((a, b) => a.span[0] - b.span[0]);
  let out = "", pos = 0;
  for (const c of spans) {
    const [s, e] = c.span;
    if (s < pos) continue;
    const r = results[c.id];
    out += esc(text.slice(pos, s)) +
      `<mark class="hl ${r ? "v-" + r.verdict : "pending"}" data-id="${esc(c.id)}" tabindex="0">${esc(text.slice(s, e))}</mark>`;
    pos = e;
  }
  out += esc(text.slice(pos));
  const missing = claims.length - spans.length;
  return `<div class="annotated">${out}</div>` +
    (missing > 0 ? `<div class="meta">${missing} claim(s) couldn't be matched to the text; they are listed below.</div>` : "");
}

function renderVerify() {
  const out = $("#verify-out");
  if (!V.claims) { out.innerHTML = loading("Finding the time-sensitive claims in this answer…"); return; }
  const claims = V.claims;
  if (!claims.length && V.phase === "done") {
    out.innerHTML = `<div class="card">No time-sensitive claims found. Nothing in this answer is likely to go stale.</div>` + usageBlock(V.report.usage, V.simulated);
    return;
  }
  const done = Object.keys(V.results).length;
  let head;
  if (V.report) {
    const r = V.report;
    const counts = VERDICTS.filter((v) => r.summary[v]).map((v) => pill(v, r.summary[v])).join("");
    const risky = r.summary.outdated + r.summary.disputed;
    head = `<div class="card summary">${gauge(r.overall)}
      <div><div class="headline">${risky ? `${risky} of ${r.results.length} claims may be out of date` : `All ${r.results.length} claims look current`}</div>
      <div class="meta" style="margin:4px 0 10px">Overall freshness score, from the age and authority of the sources, how many agree, and whether newer sources contradict</div>
      <div class="counts">${counts}</div></div></div>`;
  } else {
    const pct = claims.length ? Math.round((done / claims.length) * 100) : 0;
    const msg = V.phase === "refresh" ? "All claims checked · writing the refreshed answer…"
      : `Checked ${done} of ${claims.length} claims against the live web…`;
    head = `<div class="card progress"><div><span class="spinner"></span>${esc(msg)}</div>
      <div class="bar"><i style="width:${pct}%;background:var(--accent)"></i></div></div>`;
  }
  const r = V.report;
  out.innerHTML = `${head}
    <h2>Your answer, checked <span class="legend">${VERDICTS.slice(0, 4).map((v) => `<span class="key v-${v}">${LABEL[v]}</span>`).join("")}</span></h2>
    <div class="card">${annotated(V.text, claims, V.results)}<div class="hint">Hover or tap a highlighted claim for what live sources say now.</div></div>
    <h2>Claims</h2>${claims.map((c) => claimCard(c, V.results[c.id])).join("")}
    ${r && r.refreshed_answer ? `<h2>Refreshed answer</h2><div class="card"><div class="refreshed">${esc(r.refreshed_answer)}</div></div>` : ""}
    ${r ? usageBlock(r.usage, r.simulated_outage) : ""}`;
  if (r) refreshBudget();
}

// ---------- popover for highlighted claims ----------
const pop = document.createElement("div");
pop.className = "popover hidden";
document.body.appendChild(pop);
let pinned = null;

function showPop(mark) {
  const id = mark.dataset.id;
  const c = V?.claims?.find((x) => x.id === id);
  if (!c) return;
  const r = V.results[id];
  const top = r ? r.evidence.filter((e) => e.stance !== "unrelated").slice(0, 3) : [];
  pop.innerHTML = r ? `
    <div class="pop-head">${pill(r.verdict)}<span class="meta">freshness ${r.freshness}/100</span></div>
    ${r.current_value ? `<div class="now">Now: <b>${esc(r.current_value)}</b></div>` : r.verdict === "current" ? `<div class="now ok">Still matches live sources</div>` : ""}
    <div class="pop-reason">${esc(r.reasons[r.reasons.length - 1] || "")}</div>
    ${top.map((e) => `<div class="pop-ev"><span class="st ${e.stance}">${e.stance === "supports" ? "✓" : "✗"}</span>
      <a href="${esc(e.url)}" target="_blank" rel="noopener">${esc(e.domain)}</a><span class="meta">${esc(e.published || "undated")}</span></div>`).join("")}
    <a href="#card-${esc(id)}" class="pop-more">Details ↓</a>`
    : `<div class="meta"><span class="spinner sm"></span>Checking this claim on the live web…</div>`;
  pop.classList.remove("hidden");
  const b = mark.getBoundingClientRect();
  const w = Math.min(340, window.innerWidth - 24);
  pop.style.width = w + "px";
  pop.style.left = Math.max(12, Math.min(b.left + window.scrollX, window.scrollX + window.innerWidth - w - 12)) + "px";
  pop.style.top = b.bottom + window.scrollY + 8 + "px";
}
const hidePop = () => { if (!pinned) pop.classList.add("hidden"); };

document.addEventListener("mouseover", (e) => { const m = e.target.closest?.("mark.hl"); if (m && !pinned) showPop(m); });
document.addEventListener("mouseout", (e) => { if (e.target.closest?.("mark.hl") && !pop.contains(e.relatedTarget)) hidePop(); });
pop.addEventListener("mouseleave", hidePop);
document.addEventListener("click", (e) => {
  const m = e.target.closest?.("mark.hl");
  if (m) { pinned = pinned === m ? null : m; pinned ? showPop(m) : pop.classList.add("hidden"); return; }
  if (e.target.closest?.(".pop-more")) {
    e.preventDefault();
    const card = document.getElementById(e.target.closest(".pop-more").getAttribute("href").slice(1));
    pinned = null; pop.classList.add("hidden");
    card?.scrollIntoView({ behavior: "smooth", block: "center" });
    card?.classList.add("flash"); setTimeout(() => card?.classList.remove("flash"), 1400);
    return;
  }
  if (!pop.contains(e.target)) { pinned = null; pop.classList.add("hidden"); }
});
document.addEventListener("keydown", (e) => {
  const m = e.target.closest?.("mark.hl");
  if (m && (e.key === "Enter" || e.key === " ")) { e.preventDefault(); pinned = m; showPop(m); }
  if (e.key === "Escape") { pinned = null; pop.classList.add("hidden"); }
});

// ---------- bookmarklet ----------
// Select text on any page, click the bookmarklet: it opens StaleGuard with the text in the URL fragment
// (#check=...). Fragments never reach a server and survive Cross-Origin-Opener-Policy, unlike postMessage.
const BOOKMARKLET = `javascript:(()=>{const t=String(getSelection()).trim();if(t.length<20){alert('StaleGuard: select the AI answer (at least a sentence) first.');return}` +
  `const w=open('${location.origin}/#check='+encodeURIComponent(t.slice(0,20000))+'&from='+encodeURIComponent(location.hostname),'staleguard');` +
  `if(!w)alert('StaleGuard: allow pop-ups for this site to check selected text.')})()`;
const bm = $("#bookmarklet");
if (bm) {
  bm.href = BOOKMARKLET;
  bm.addEventListener("click", (e) => { e.preventDefault(); alert("Drag this button to your bookmarks bar, then select an AI answer on any page and click the bookmark."); });
}

function checkFromHash() {
  const p = new URLSearchParams(location.hash.slice(1));
  const text = p.get("check");
  if (!text) return;
  history.replaceState(null, "", location.pathname + location.search);   // don't keep the text in the URL
  document.querySelector('.tab[data-tab="verify"]').click();
  $("#answer").value = text;
  const from = p.get("from");
  $("#from-note").innerHTML = from ? `Text selected on <b>${esc(from)}</b>, sent by the StaleGuard bookmarklet` : "";
  $("#verify-form").requestSubmit();
}
window.addEventListener("hashchange", checkFromHash);   // pop-up already open: only the fragment changes
checkFromHash();

// ---------- brief ----------
(() => { // default meeting time: tomorrow 10:00
  const d = new Date(); d.setDate(d.getDate() + 1); d.setHours(10, 0, 0, 0);
  $("#meeting").value = new Date(d - d.getTimezoneOffset() * 60000).toISOString().slice(0, 16);
})();

async function loadBriefList() {
  try {
    const list = await api("/api/briefs");
    $("#brief-list").innerHTML = list.map((b) =>
      `<button class="brief-chip" data-id="${esc(b.id)}">${esc(b.entity)} · ${new Date(b.meeting_time).toLocaleString([], { dateStyle: "medium", timeStyle: "short" })}</button>`).join("");
    document.querySelectorAll(".brief-chip").forEach((c) =>
      c.addEventListener("click", async () => renderBrief(await api(`/api/briefs/${c.dataset.id}`))));
  } catch { /* ignore */ }
}

$("#brief-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const btn = $("#brief-btn");
  btn.disabled = true;
  $("#brief-out").innerHTML = loading("Researching the last 30 days, writing the brief, then verifying every development…");
  try {
    const body = { entity: $("#entity").value.trim(), purpose: $("#purpose").value.trim(),
                   meeting_time: new Date($("#meeting").value).toISOString(), simulate_outage: $("#outage-brief").checked };
    renderBrief(await api("/api/briefs", { method: "POST", body: JSON.stringify(body) }));
    loadBriefList();
  } catch (err) { $("#brief-out").innerHTML = errorBox(err); }
  btn.disabled = false;
});

function renderBrief(b) {
  const srcByUrl = Object.fromEntries(b.sources.map((s) => [s.url, s]));
  const meeting = new Date(b.meeting_time);
  const mins = Math.round((meeting - new Date()) / 60000);
  const when = mins > 0 ? `in ${mins >= 1440 ? Math.round(mins / 1440) + " day(s)" : mins >= 60 ? Math.round(mins / 60) + " h" : mins + " min"}` : "past";
  const devs = b.developments.map((r) => {
    const cites = r.claim.source_urls.map((u) => srcByUrl[u]).filter(Boolean)
      .map((s) => `<a href="${esc(s.url)}" target="_blank" rel="noopener">[${s.n}]</a>`).join(" ");
    return `<div class="dev">${pill(r.verdict)}<div>${esc(r.claim.text)} <span class="cites">${cites}</span>
      ${r.current_value ? `<div class="fix">Newer sources say: ${esc(r.current_value)}</div>` : ""}</div></div>`;
  }).join("");
  const li = (xs) => xs.map((x) => `<li>${esc(x)}</li>`).join("");
  const checks = b.checks.slice().reverse().map((c) => `<div class="check">${new Date(c.at).toLocaleString()} · <b>${c.trigger.replace("_", "-")}</b>
      ${c.trigger === "created" ? "" : c.changes.length ? `<div class="changes">${c.changes.map(esc).join("<br>")}</div>` : " · no changes"}</div>`).join("");

  $("#brief-out").innerHTML = `
    <div class="actions">
      <button class="ghost" id="recheck">Re-check now</button>
      <button class="ghost" onclick="window.print()">Print / PDF</button>
    </div>
    <div class="paper">
      <div class="title"><h3>${esc(b.entity)}</h3>
        <span class="sub">Meeting ${meeting.toLocaleString([], { dateStyle: "medium", timeStyle: "short" })} (${when})${b.purpose ? " · " + esc(b.purpose) : ""}</span></div>
      <p class="one">${esc(b.content.one_liner)}</p>
      <h2>Last 30 days (each one checked against the live web)</h2>${devs || "<p>No notable developments found.</p>"}
      <h2>Talking points</h2><ul>${li(b.content.talking_points)}</ul>
      <h2>Open questions</h2><ul>${li(b.content.open_questions)}</ul>
      ${b.content.watch_outs.length ? `<h2>Watch-outs</h2><ul>${li(b.content.watch_outs)}</ul>` : ""}
      <h2>Sources</h2><ol class="sources">${b.sources.map((s) =>
        `<li><a href="${esc(s.url)}" target="_blank" rel="noopener">${esc(s.title || s.domain)}</a> · ${esc(s.domain)} · ${esc(s.published || "undated")}</li>`).join("")}</ol>
    </div>
    <div class="card checks"><b>Freshness checks</b>${b.pre_meeting_checked ? " · pre-meeting re-check done" : ` · auto re-check runs shortly before the meeting`}${checks}</div>
    ${usageBlock(b.usage, false)}`;
  refreshBudget();

  $("#recheck").addEventListener("click", async (ev) => {
    ev.target.disabled = true; ev.target.textContent = "Re-checking…";
    try { renderBrief(await api(`/api/briefs/${b.id}/recheck`, { method: "POST" })); }
    catch (err) { ev.target.disabled = false; ev.target.textContent = "Re-check failed, retry"; ev.target.title = err.message; }
  });
}
