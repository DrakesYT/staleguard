// StaleGuard frontend: vanilla JS, no build step.
const $ = (s) => document.querySelector(s);
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const COLORS = { current: "var(--current)", aging: "var(--aging)", disputed: "var(--disputed)", outdated: "var(--outdated)", unverified: "var(--unverified)" };
const LABEL = { current: "Current", aging: "Aging", disputed: "Disputed", outdated: "Outdated", unverified: "Unverified" };

const SAMPLE = `Here's a quick overview. OpenAI's flagship model is GPT-4, and ChatGPT Plus costs $20 per month. The newest stable Python release is Python 3.11. Twitter's CEO is Parag Agrawal. The EU AI Act is still being negotiated and has not been adopted. Stripe was last valued at $95 billion. React's latest major version is React 18.`;

async function api(path, opts = {}) {
  const r = await fetch(path, { headers: { "Content-Type": "application/json" }, ...opts });
  const body = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(body.detail || `HTTP ${r.status}`);
  return body;
}
const loading = (msg) => `<div class="loading"><span class="spinner"></span>${esc(msg)}</div>`;
const errorBox = (e) => `<div class="error">${esc(e.message || e)}</div>`;

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
    $("#health").innerHTML =
      `<span class="dot" style="background:${ok ? "var(--current)" : "var(--outdated)"}"></span>` +
      (h.mock ? "Offline demo mode" : `Bifrost ${h.bifrost.reachable ? "connected" : "unreachable"} · Tavily ${h.tavily_key_set ? "ready" : "key missing"}`) +
      `<br>${esc(h.models.fast)}${h.models.fallbacks.length ? " → " + esc(h.models.fallbacks.join(" → ")) : ""}`;
  } catch { $("#health").textContent = "API offline"; }
})();

// ---------- shared renderers ----------
function gauge(score) {
  const color = score >= 70 ? "var(--current)" : score >= 45 ? "var(--aging)" : "var(--outdated)";
  return `<div class="gauge" style="background:conic-gradient(${color} ${score * 3.6}deg, var(--line) 0)"><span>${score}</span></div>`;
}
const pill = (v, n) => `<span class="pill v-${v}">${LABEL[v]}${n !== undefined ? ` · ${n}` : ""}</span>`;

function usageBlock(u) {
  const served = Object.entries(u.served_by).map(([k, v]) => `${esc(k)} ×${v}`).join(", ") || "-";
  return `<div class="card usage-card"><div class="usage">
    <span>LLM calls <b>${u.llm_calls}</b></span>
    <span>Tokens <b>${(u.prompt_tokens + u.completion_tokens).toLocaleString()}</b></span>
    <span>Est. cost <b>$${u.cost_usd.toFixed(4)}</b></span>
    <span>Fallbacks <b>${u.fallbacks_used}</b></span>
    <span>Tavily searches <b>${u.tavily_searches}</b> (+${u.cache_hits} cached)</span>
    <span>Served by <b>${served}</b></span></div></div>`;
}

function claimCard(r) {
  const c = r.claim;
  const ev = r.evidence.map((e) => `
    <div class="ev"><span class="st ${e.stance}">${e.stance}</span>
      <span><a href="${esc(e.url)}" target="_blank" rel="noopener">${esc(e.title || e.domain)}</a>
        <span class="meta">${esc(e.domain)}${e.note ? " · " + esc(e.note) : ""}</span></span>
      <span class="date">${esc(e.published || "undated")}</span></div>`).join("");
  return `<div class="claim ${r.verdict}">
    <div class="claim-head"><div class="claim-text">${esc(c.text)}</div>${pill(r.verdict)}</div>
    <div class="meta">${esc(c.category.replace("_", " "))}${c.value ? " · claimed: " + esc(c.value) : ""} · freshness ${r.freshness}/100</div>
    ${r.current_value ? `<div class="now">Live sources now say: <b>${esc(r.current_value)}</b></div>` : ""}
    <div class="bar"><i style="width:${r.freshness}%;background:${COLORS[r.verdict]}"></i></div>
    <details><summary>Why · ${r.evidence.length} sources</summary>
      <ul class="reasons">${r.reasons.map((x) => `<li>${esc(x)}</li>`).join("")}</ul>${ev}</details>
  </div>`;
}

// ---------- verify ----------
$("#sample").addEventListener("click", () => ($("#answer").value = SAMPLE));
$("#verify-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const text = $("#answer").value.trim();
  if (text.length < 20) return;
  const btn = $("#verify-btn");
  btn.disabled = true;
  $("#verify-out").innerHTML = loading("Extracting time-sensitive claims and re-checking each one on the live web…");
  try {
    renderReport(await api("/api/verify", { method: "POST", body: JSON.stringify({ text }) }));
  } catch (err) { $("#verify-out").innerHTML = errorBox(err); }
  btn.disabled = false;
});

function renderReport(r) {
  if (!r.results.length) {
    $("#verify-out").innerHTML = `<div class="card">No time-sensitive claims found. Nothing in this answer is likely to go stale.</div>` + usageBlock(r.usage);
    return;
  }
  const counts = Object.entries(r.summary).filter(([, n]) => n).map(([v, n]) => pill(v, n)).join("");
  const risky = r.summary.outdated + r.summary.disputed;
  $("#verify-out").innerHTML = `
    <div class="card summary">${gauge(r.overall)}
      <div><div style="font-size:17px;font-weight:600">${risky ? `${risky} of ${r.results.length} claims may be out of date` : `All ${r.results.length} claims look current`}</div>
      <div class="meta" style="margin:4px 0 10px">Overall freshness score, from the age of the sources, how many agree, and whether newer sources contradict</div>
      <div class="counts">${counts}</div></div></div>
    ${r.results.map(claimCard).join("")}
    ${r.refreshed_answer ? `<h2>Refreshed answer</h2><div class="card"><div class="refreshed">${esc(r.refreshed_answer)}</div></div>` : ""}
    ${usageBlock(r.usage)}`;
}

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
                   meeting_time: new Date($("#meeting").value).toISOString() };
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
    ${usageBlock(b.usage)}`;

  $("#recheck").addEventListener("click", async (ev) => {
    ev.target.disabled = true; ev.target.textContent = "Re-checking…";
    try { renderBrief(await api(`/api/briefs/${b.id}/recheck`, { method: "POST" })); }
    catch (err) { ev.target.disabled = false; ev.target.textContent = "Re-check failed, retry"; ev.target.title = err.message; }
  });
}
