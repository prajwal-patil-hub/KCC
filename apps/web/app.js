// ALOS KCC Lending Workspace — drives the full lifecycle against the FastAPI
// backend, rendering a workflow timeline + health score derived from the event
// log. AI is optional: when it isn't running, the memo step offers template /
// manual / skip instead of blocking.

const $ = (id) => document.getElementById(id);
let appId = null;
let aiAvailable = false;

// Distinct identities so Separation of Duties (maker != checker) holds, and so
// each privileged stage carries the role the workflow requires.
function headers(role) {
  const base = ($("user").value || "officer").trim();
  let user = base, roles = "Maker,Checker,SanctionAuthority";
  if (role === "checker") user = base + ".checker";
  if (role === "authority") user = base + ".authority";
  return {
    "Content-Type": "application/json",
    "X-User-Id": user,
    "X-Tenant-Id": $("tenant").value || "bankA",
    "X-Roles": roles,
  };
}

function toast(msg, ms = 3000) {
  const t = $("toast");
  t.textContent = msg; t.classList.remove("hidden");
  clearTimeout(toast._t); toast._t = setTimeout(() => t.classList.add("hidden"), ms);
}

async function api(method, path, body, role) {
  const res = await fetch(path, {
    method, headers: headers(role), body: body ? JSON.stringify(body) : undefined,
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    const d = typeof data.detail === "object" ? JSON.stringify(data.detail) : data.detail;
    throw new Error(d || `${res.status} ${res.statusText}`);
  }
  return data;
}

async function refreshAi() {
  try {
    const h = await api("GET", "/ai/health");
    aiAvailable = h.ai_available;
    const b = $("aiBadge");
    b.textContent = aiAvailable ? `AI: ${h.provider} ✓` : "AI: not running";
    b.className = "badge " + (aiAvailable ? "badge-ok" : "badge-warn");
  } catch { $("aiBadge").textContent = "AI: unknown"; }
}

function showOut(title, obj) {
  $("out").textContent = typeof obj === "string" ? obj : JSON.stringify(obj, null, 2);
  $("out").classList.remove("hidden");
  $("meta").innerHTML = `<span class="tag">${title}</span>`;
  $("meta").classList.remove("hidden");
}

function showMemo(memo) {
  showOut(`mode: ${memo.mode}`, memo.narrative || "(step skipped)");
  const tags = [`mode: ${memo.mode}`, memo.ai_available ? "AI: available" : "AI: unavailable"];
  if (memo.confidence != null) tags.push(`confidence: ${memo.confidence}`);
  if (memo.fallback_reason) tags.push(memo.fallback_reason);
  if (memo.note) tags.push(`note: ${memo.note}`);
  $("meta").innerHTML = tags.map((t) => `<span class="tag">${t}</span>`).join("");
}

// --- timeline + stage-aware actions --------------------------------------
const ACTIONS = {
  EligibilityComputed: (t) => {
    const notice = $("aiNotice");
    if (!aiAvailable) {
      notice.classList.remove("hidden");
      notice.innerHTML = "⚠️ <b>AI is not running.</b> Use a deterministic template memo, " +
        "write one manually, or skip the step — the workflow won't block.";
    } else notice.classList.add("hidden");
    t.title = "Credit memo";
    const ai = btn("✨ Generate with AI", () => memo("generate"), "primary", !aiAvailable);
    return [ai,
      btn("📄 Use template memo", () => memo("generate")),
      btn("✍️ Write manually", () => toggle("manualBox")),
      btn("⤼ Skip step…", () => toggle("skipBox"), "ghost")];
  },
  MemoGenerated: (t) => { t.title = "Maker review"; $("aiNotice").classList.add("hidden");
    return [btn("✔ Maker review", () => advance("MakerReviewed"), "primary")]; },
  MakerReviewed: (t) => { t.title = "Checker review (independent user)";
    return [btn("✔ Checker review", () => advance("CheckerReviewed", "checker"), "primary")]; },
  CheckerReviewed: (t) => { t.title = "Sanction";
    return [btn("🏛 Sanction (authority)", () => advance("Sanctioned", "authority"), "primary")]; },
  Sanctioned: (t) => { t.title = "Documentation (NESL · eStamp · eSign)";
    return [btn("📑 Execute documents", () => post(`/applications/${appId}/documents/execute`,
      (d) => showOut("documents", d.documents)), "primary")]; },
  DocumentsExecuted: (t) => { t.title = "Disbursement";
    return [btn("💸 Disburse", () => post(`/applications/${appId}/disburse`,
      (d) => showOut(d.idempotent_replay ? "idempotent replay" : "disbursed", d.disbursement)), "primary")]; },
  Disbursed: (t) => { t.title = "Post to CBS ledger";
    return [btn("🧾 Post to CBS", () => post(`/applications/${appId}/cbs-post`,
      (d) => showOut("cbs", d.cbs)), "primary")]; },
  CbsPosted: (t) => { t.title = "Complete — reconcile";
    return [btn("✅ Reconciliation report", async () =>
      showOut("reconciliation", await api("GET", "/reconciliation/report")), "primary")]; },
};

function btn(label, onclick, cls = "", disabled = false) {
  const b = document.createElement("button");
  b.textContent = label; if (cls) b.className = cls; b.disabled = disabled;
  b.onclick = onclick; return b;
}
function toggle(id) { $(id).classList.toggle("hidden"); }

async function renderTimeline() {
  if (!appId) return;
  const t = await api("GET", `/applications/${appId}/timeline`);
  $("flowCard").style.display = "block";
  $("timeline").innerHTML = "";
  const doneNames = t.timeline.filter((s) => s.status === "done").map((s) => s.name);
  const current = t.timeline.find((s) => s.status !== "done");
  t.timeline.forEach((s) => {
    const cls = s.status === "done" ? "done" : (current && s.name === current.name ? "current" : "pending");
    const node = document.createElement("div");
    node.className = "node " + cls;
    node.innerHTML = `<span class="dot"></span> ${s.name}` +
      (s.requires_checker ? ' <small>· checker</small>' : "") +
      (s.automated ? ' <small>· auto</small>' : "");
    $("timeline").appendChild(node);
  });

  // health ring
  $("health").classList.remove("hidden");
  $("ring").style.setProperty("--val", t.health_score);
  $("healthNum").textContent = t.health_score + (t.flags.includes("memo_skipped") ? "⚠" : "");

  // stage-aware action buttons
  const titleObj = { title: "Done" };
  const actions = $("actions"); actions.innerHTML = "";
  const builder = current ? ACTIONS[current.name] : null;
  if (builder) builder(titleObj).forEach((b) => actions.appendChild(b));
  else if (!current) { $("actionTitle").textContent = "🎉 Lifecycle complete";
    actions.appendChild(btn("✅ Reconciliation report", async () =>
      showOut("reconciliation", await api("GET", "/reconciliation/report")), "primary")); return; }
  $("actionTitle").textContent = titleObj.title;
}

async function advance(stage, role) {
  try { await api("POST", `/applications/${appId}/advance/${stage}`, {}, role);
    toast(`→ ${stage}`); await renderTimeline(); }
  catch (e) { toast("Error: " + e.message); }
}
async function post(path, onok) {
  try { const d = await api("POST", path); if (onok) onok(d); toast("Done"); await renderTimeline(); }
  catch (e) { toast("Error: " + e.message); }
}
async function memo(kind) {
  try { const d = await api("POST", `/applications/${appId}/memo/${kind}`); showMemo(d.memo);
    await renderTimeline(); } catch (e) { toast("Error: " + e.message); }
}

// --- bootstrap an application --------------------------------------------
$("seedBtn").onclick = async () => {
  try {
    const lead = await api("POST", "/applications",
      { applicant_name: $("applicant").value, mobile: "9999999999", product: "KCC" });
    appId = lead.application_id;
    await api("POST", `/applications/${appId}/link-customer`,
      { customer_id: "C-" + appId.slice(0, 6), farmer_class: "small" });
    await api("POST", `/applications/${appId}/kyc`,
      { aadhaar_number: "1234 5678 9012", name: $("applicant").value });
    const e = await api("POST", `/assessment/${appId}/eligibility`, {
      parcels: [{ parcel_id: "P1", area_hectares: 2.0, verified: true }],
      crops: [{ parcel_id: "P1", crop: "wheat", season: "rabi", area_hectares: 2.0 }],
    });
    $("appInfo").classList.remove("hidden");
    $("appInfo").innerHTML =
      `<b>Application</b><span>${appId}</span>` +
      `<b>Eligible</b><span>${e.eligible}</span>` +
      `<b>Net KCC limit</b><span>Rs ${Number(e.breakup.net_limit).toLocaleString("en-IN")}</span>` +
      `<b>Collateral-free</b><span>${e.collateral_free}</span>` +
      `<b>PSL</b><span>${e.psl_category}</span>`;
    await renderTimeline();
    toast("Application at eligibility — proceed below.");
  } catch (e) { toast("Error: " + e.message); }
};
$("resetBtn").onclick = () => { appId = null; $("flowCard").style.display = "none";
  $("appInfo").classList.add("hidden"); $("out").classList.add("hidden");
  $("meta").classList.add("hidden"); $("health").classList.add("hidden"); };

$("manualSave").onclick = async () => {
  const text = $("manualText").value.trim(); if (!text) return toast("Write something first.");
  try { const d = await api("POST", `/applications/${appId}/memo/manual`, { text });
    showMemo(d.memo); $("manualBox").classList.add("hidden"); await renderTimeline(); }
  catch (e) { toast("Error: " + e.message); }
};
$("skipSave").onclick = async () => {
  const reason = $("skipReason").value.trim();
  if (reason.length < 3) return toast("A reason is required to skip (it is audited).");
  try { const d = await api("POST", `/applications/${appId}/memo/skip`, { reason });
    showMemo(d.memo); $("skipBox").classList.add("hidden"); await renderTimeline(); }
  catch (e) { toast("Error: " + e.message); }
};

refreshAi();
