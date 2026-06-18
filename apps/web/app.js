// ALOS Credit Memo Workspace — talks to the FastAPI backend on the same origin.
// Demonstrates graceful handling when AI is not running: the AI button is
// disabled and a notice surfaces the fallback options (template / manual / skip).

const $ = (id) => document.getElementById(id);
let appId = null;
let aiAvailable = false;

function headers() {
  return {
    "Content-Type": "application/json",
    "X-User-Id": $("user").value || "maker1",
    "X-Tenant-Id": $("tenant").value || "bankA",
    "X-Roles": "Maker,Checker",
  };
}

function toast(msg, ms = 2600) {
  const t = $("toast");
  t.textContent = msg;
  t.classList.remove("hidden");
  clearTimeout(toast._t);
  toast._t = setTimeout(() => t.classList.add("hidden"), ms);
}

async function api(method, path, body) {
  const res = await fetch(path, {
    method,
    headers: headers(),
    body: body ? JSON.stringify(body) : undefined,
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.detail || `${res.status} ${res.statusText}`);
  return data;
}

async function refreshAi() {
  try {
    const h = await api("GET", "/ai/health");
    aiAvailable = h.ai_available;
    const badge = $("aiBadge");
    badge.textContent = aiAvailable ? `AI: ${h.provider} ✓` : "AI: not running";
    badge.className = "badge " + (aiAvailable ? "badge-ok" : "badge-warn");

    $("genAiBtn").disabled = !aiAvailable;
    $("genAiBtn").title = aiAvailable
      ? "Generate using AI"
      : "AI is not running — use a template memo, write manually, or skip";

    const notice = $("aiNotice");
    if (!aiAvailable) {
      notice.classList.remove("hidden", "ok");
      notice.innerHTML =
        "⚠️ <b>AI underwriting is not running.</b> " + h.message +
        " You can still proceed — the deterministic <b>template memo</b> is always available.";
    } else {
      notice.classList.add("hidden");
    }
  } catch (e) {
    $("aiBadge").textContent = "AI: unknown";
  }
}

function showMemo(memo) {
  $("memoOut").textContent = memo.narrative || "(no narrative — step skipped)";
  $("memoOut").classList.remove("hidden");
  const tags = [`mode: ${memo.mode}`];
  if (memo.confidence != null) tags.push(`confidence: ${memo.confidence}`);
  if (memo.model) tags.push(`model: ${memo.model}`);
  tags.push(memo.ai_available ? "AI: available" : "AI: unavailable");
  if (memo.fallback_reason) tags.push(memo.fallback_reason);
  if (memo.note) tags.push(`note: ${memo.note}`);
  $("memoMeta").innerHTML = tags.map((t) => `<span class="tag">${t}</span>`).join("");
  $("memoMeta").classList.remove("hidden");
}

// --- Step 1: seed an application -----------------------------------------
$("seedBtn").onclick = async () => {
  try {
    const lead = await api("POST", "/applications", {
      applicant_name: $("applicant").value, mobile: "9999999999", product: "KCC",
    });
    appId = lead.application_id;
    await api("POST", `/applications/${appId}/link-customer`,
      { customer_id: "C-" + appId.slice(0, 6), farmer_class: "small" });
    await api("POST", `/applications/${appId}/kyc`,
      { aadhaar_number: "1234 5678 9012", name: $("applicant").value });
    const elig = await api("POST", `/assessment/${appId}/eligibility`, {
      parcels: [{ parcel_id: "P1", area_hectares: 2.0, verified: true }],
      crops: [{ parcel_id: "P1", crop: "wheat", season: "rabi", area_hectares: 2.0 }],
    });
    const info = $("appInfo");
    info.classList.remove("hidden");
    info.innerHTML =
      `<b>Application</b><span>${appId}</span>` +
      `<b>Eligible</b><span>${elig.eligible}</span>` +
      `<b>Net KCC limit</b><span>Rs ${Number(elig.breakup.net_limit).toLocaleString("en-IN")}</span>` +
      `<b>Collateral-free</b><span>${elig.collateral_free}</span>`;
    toast("Application ready at eligibility stage.");
  } catch (e) { toast("Error: " + e.message); }
};

// --- Step 2: memo actions -------------------------------------------------
function needApp() {
  if (!appId) { toast("Create an application first (step 1)."); return false; }
  return true;
}

$("genAiBtn").onclick = async () => {
  if (!needApp()) return;
  try { showMemo((await api("POST", `/applications/${appId}/memo/generate`)).memo); }
  catch (e) { toast("Error: " + e.message); }
};
$("genTplBtn").onclick = async () => {
  if (!needApp()) return;
  // Same endpoint: with AI off it returns a template memo automatically.
  try { showMemo((await api("POST", `/applications/${appId}/memo/generate`)).memo); }
  catch (e) { toast("Error: " + e.message); }
};
$("manualBtn").onclick = () => { $("manualBox").classList.toggle("hidden"); $("skipBox").classList.add("hidden"); };
$("skipBtn").onclick = () => { $("skipBox").classList.toggle("hidden"); $("manualBox").classList.add("hidden"); };

$("manualSave").onclick = async () => {
  if (!needApp()) return;
  const text = $("manualText").value.trim();
  if (!text) return toast("Write something first.");
  try {
    showMemo((await api("POST", `/applications/${appId}/memo/manual`, { text })).memo);
    $("manualBox").classList.add("hidden");
  } catch (e) { toast("Error: " + e.message); }
};

$("skipSave").onclick = async () => {
  if (!needApp()) return;
  const reason = $("skipReason").value.trim();
  if (reason.length < 3) return toast("A reason is required to skip (it is audited).");
  try {
    showMemo((await api("POST", `/applications/${appId}/memo/skip`, { reason })).memo);
    $("skipBox").classList.add("hidden");
  } catch (e) { toast("Error: " + e.message); }
};

refreshAi();
