from fastapi import APIRouter
from fastapi.responses import HTMLResponse

router = APIRouter(prefix="/admin", tags=["Admin"])

HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Scrapfly Admin - ImageFactory</title>
<style>
* { margin: 0; padding: 0; box-sizing: border-box; }
body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: #09090b; color: #e4e4e7; padding: 2rem; }
h1 { font-size: 1.5rem; font-weight: 700; margin-bottom: 0.25rem; }
h2 { font-size: 1.1rem; font-weight: 600; margin: 1.5rem 0 0.75rem; }
p.sub { color: #a1a1aa; font-size: 0.875rem; margin-bottom: 1.5rem; }
.grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(140px, 1fr)); gap: 0.75rem; margin-bottom: 1rem; }
.card { background: #18181b; border: 1px solid #27272a; border-radius: 0.5rem; padding: 1rem; text-align: center; }
.card .val { font-size: 1.75rem; font-weight: 700; }
.card .lbl { font-size: 0.75rem; color: #a1a1aa; margin-top: 0.25rem; }
.card.warn { border-color: #ef4444; }
.card.success { border-color: #22c55e; }
table { width: 100%; border-collapse: collapse; font-size: 0.875rem; }
th { text-align: left; padding: 0.5rem; color: #a1a1aa; border-bottom: 1px solid #27272a; }
td { padding: 0.5rem; border-bottom: 1px solid #27272a; vertical-align: middle; }
tr:last-child td { border-bottom: none; }
.fade { animation: fadeIn 0.3s ease; }
@keyframes fadeIn { from { opacity: 0; transform: translateY(4px); } to { opacity: 1; transform: translateY(0); } }
.loading { text-align: center; padding: 2rem; color: #a1a1aa; }
.error { text-align: center; padding: 2rem; color: #ef4444; }
.success-msg { color: #22c55e; font-size: 0.875rem; margin: 0.5rem 0; }
.back { display: inline-block; margin-bottom: 1rem; color: #a1a1aa; text-decoration: none; font-size: 0.875rem; }
.back:hover { color: #e4e4e7; }
input[type=text] { background: #18181b; border: 1px solid #27272a; border-radius: 0.375rem; color: #e4e4e7; padding: 0.5rem 0.75rem; font-size: 0.875rem; width: 100%; }
button { background: #27272a; border: 1px solid #3f3f46; border-radius: 0.375rem; color: #e4e4e7; padding: 0.5rem 1rem; font-size: 0.875rem; cursor: pointer; }
button:hover { background: #3f3f46; }
button.danger { border-color: #ef4444; color: #ef4444; }
button.danger:hover { background: #ef4444; color: #fff; }
button.primary { background: #6366f1; border-color: #6366f1; }
button.primary:hover { background: #818cf8; }
.form-row { display: flex; gap: 0.5rem; margin-bottom: 0.75rem; align-items: center; }
.flex { display: flex; gap: 0.75rem; align-items: center; }
.tag { display: inline-block; background: #27272a; border-radius: 9999px; padding: 0.125rem 0.5rem; font-size: 0.75rem; color: #a1a1aa; }
pre { font-family: monospace; font-size: 0.8rem; }
</style>
</head>
<body>
<a href="/" class="back">&larr; Back to Dashboard</a>
<h1>&#x26A1; Scrapfly Admin</h1>
<p class="sub">API key management, credit monitoring, and retry controls</p>

<div id="app"><div class="loading">Loading...</div></div>

<script>
async function api(url, opts) {
  const resp = await fetch(url, { headers: { 'Content-Type': 'application/json', 'X-API-Key': 'dev-api-key-12345' }, ...opts });
  if (!resp.ok) { const t = await resp.text(); throw new Error(t); }
  return resp.json();
}

function showMsg(el, text, type) {
  el.innerHTML = '<p class="' + type + '-msg fade">' + text + '</p>';
  setTimeout(() => el.innerHTML = '', 3000);
}

async function load() {
  try {
    const d = await api('/api/v1/admin/scrapfly/usage');
    const pct = d.monthly_budget > 0 ? Math.round((d.total_cost / d.monthly_budget) * 100) : 0;
    const warn = pct > 80 ? 'warn' : '';
    const keyRows = (d.keys || []).map(k => '<tr><td><code>' + escapeHtml(k.key_preview) + '</code></td><td>' + k.used + '</td><td>' + k.remaining + '</td></tr>').join('');
    document.getElementById('app').innerHTML = `
      <div class="grid fade">
        <div class="card ${warn}"><div class="val">${d.total_cost}</div><div class="lbl">Credits Used</div></div>
        <div class="card"><div class="val">${d.remaining_credits}</div><div class="lbl">Remaining</div></div>
        <div class="card"><div class="val">${d.budget_left}</div><div class="lbl">Budget Left</div></div>
        <div class="card"><div class="val">${d.products_possible}</div><div class="lbl">Products Possible</div></div>
        <div class="card"><div class="val">${pct}%</div><div class="lbl">of ${d.monthly_budget} used</div></div>
      </div>
      ${pct > 80 ? '<p style="color:#ef4444;font-size:0.875rem;margin-bottom:1rem;">Warning: over 80% of monthly budget consumed</p>' : ''}

      <h2>Scrapfly API Keys</h2>
      <div id="key-list">
        <table class="fade"><thead><tr><th>Key</th><th>Used</th><th>Remaining</th></tr></thead>
        <tbody>${keyRows || '<tr><td colspan="3" style="text-align:center;color:#a1a1aa;">No keys configured</td></tr>'}</tbody></table>
      </div>
      <div style="margin-top:0.75rem;">
        <div class="form-row">
          <input type="text" id="new-key-input" placeholder="scp-live-xxxxxxxx..." style="flex:1;">
          <button class="primary" onclick="addKey()">Add Key</button>
        </div>
        <div id="key-msg"></div>
      </div>

      <h2>Batch Retry</h2>
      <p style="color:#a1a1aa;font-size:0.875rem;margin-bottom:0.5rem;">Re-queue all failed/error product links for scraping</p>
      <button class="danger" onclick="retryFailed()" id="retry-btn">Retry All Failed Products</button>
      <div id="retry-msg"></div>
    `;
  } catch(e) {
    document.getElementById('app').innerHTML = '<div class="error">Failed to load: ' + escapeHtml(e.message) + '</div>';
  }
}

function escapeHtml(s) { return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;'); }

async function addKey() {
  const input = document.getElementById('new-key-input');
  const key = input.value.trim();
  if (!key) return;
  try {
    await api('/api/v1/admin/scrapfly/keys', { method: 'POST', body: JSON.stringify({ key }) });
    input.value = '';
    showMsg(document.getElementById('key-msg'), 'Key added successfully', 'success');
    load();
  } catch(e) {
    showMsg(document.getElementById('key-msg'), 'Error: ' + e.message, 'error');
  }
}

async function retryFailed() {
  const btn = document.getElementById('retry-btn');
  btn.disabled = true; btn.textContent = 'Retrying...';
  try {
    const r = await api('/api/v1/admin/products/retry-failed', { method: 'POST', body: '{}' });
    showMsg(document.getElementById('retry-msg'), r.message + ' (batch: ' + r.batch_id + ')', 'success');
  } catch(e) {
    showMsg(document.getElementById('retry-msg'), 'Error: ' + e.message, 'error');
  }
  btn.disabled = false; btn.textContent = 'Retry All Failed Products';
}

load();
setInterval(load, 30000);
</script>
</body>
</html>"""


@router.get("/scrapfly/page", response_class=HTMLResponse)
async def scrapfly_admin_page():
    return HTML
