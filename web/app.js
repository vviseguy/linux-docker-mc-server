const sDot = document.getElementById('s-dot');
const sText = document.getElementById('s-text');
const sPlayers = document.getElementById('s-players');
const lastBackupEl = document.getElementById('last-backup');
const chatInput = document.getElementById('chatInput');
const chatHistory = document.getElementById('chatHistory');
const logEl = document.getElementById('log');
const LOG_KEY = 'mc-console-log';
const serverNameEl = document.getElementById('server-name');
function cfg() {
    const base = (window.CONFIG?.API_BASE || '').replace(/\/$/, '');
    const token = window.CONFIG?.API_TOKEN || '';
    return { base, token };
}
function setStatus(status) {
    sText.textContent = status || 'unknown';
    sDot.classList.remove('ok', 'err');
    if (status === 'running') {
        sDot.classList.add('ok');
    }
    else if (status === 'exited' || status === 'not-found' || status === 'not-created') {
        sDot.classList.add('err');
    }
}
function setLog(text) {
    if (logEl)
        logEl.textContent = text;
    try {
        localStorage.setItem(LOG_KEY, text);
    }
    catch { }
}
function toast(msg, type = 'info', timeout = 3500) {
    const host = document.getElementById('toasts');
    if (!host)
        return;
    const el = document.createElement('div');
    el.className = `toast ${type}`;
    el.textContent = msg;
    host.appendChild(el);
    const t = window.setTimeout(() => {
        el.style.opacity = '0';
        el.style.transform = 'translateY(6px)';
        window.setTimeout(() => { if (el.parentNode)
            host.removeChild(el); }, 250);
    }, timeout);
    el.addEventListener('click', () => { window.clearTimeout(t); if (el.parentNode)
        host.removeChild(el); });
}
function isLikelyHtml(raw, ct) {
    const type = (ct || '').toLowerCase();
    return (!type.includes('application/json') && /text\/html|<\s*!doctype|<\s*html/i.test(raw));
}
async function doCall(path, method = 'GET') {
    const { base, token } = cfg();
    if (!base || !token) {
        setLog('Configure API base and token.');
        return;
    }
    try {
        const res = await fetch(`${base}/${path}`, { method, headers: { 'Authorization': `Bearer ${token}` } });
        const raw = await res.text();
        let parsed = null;
        try {
            parsed = JSON.parse(raw);
        }
        catch { }
        const bodyForLog = isLikelyHtml(raw, res.headers.get('content-type') || '') ? '[HTML response omitted]' : raw;
        const pretty = parsed ? JSON.stringify(parsed, null, 2) : bodyForLog;
        if (!res.ok) {
            const msg = (parsed && (parsed.detail || parsed.message)) || `${res.status} ${res.statusText}`;
            setLog(`${res.status} ${res.statusText}\n${pretty}`);
            toast(msg, 'error');
        }
        else {
            setLog(`${res.status} ${res.statusText}\n${pretty}`);
        }
        if (path === 'status' && res.ok) {
            try {
                const data = parsed ?? JSON.parse(raw);
                setStatus(data?.container?.status);
                if (data?.server_name) {
                    serverNameEl.textContent = data.server_name;
                }
                const players = data?.players || [];
                sPlayers.textContent = players.length ? players.join(', ') : 'none';
                if (data?.last_backup) {
                    const d = new Date(data.last_backup * 1000);
                    lastBackupEl.textContent = d.toLocaleString();
                }
                else {
                    lastBackupEl.textContent = 'never';
                }
            }
            catch { /* ignore */ }
        }
        else if (['start', 'restart', 'stop'].includes(path)) {
            await doCall('status');
        }
    }
    catch (e) {
        setLog('Error: ' + e);
        toast(String(e), 'error');
    }
}
async function loadChat() {
    const { base, token } = cfg();
    if (!base || !token) {
        return;
    }
    try {
        const res = await fetch(`${base}/chat/history?lines=400`, { headers: { 'Authorization': `Bearer ${token}` } });
        const data = await res.json();
        renderChat(data?.messages || []);
    }
    catch { /* ignore */ }
}
function escapeHtml(s) {
    return String(s).replaceAll('&', '&amp;').replaceAll('<', '&lt;').replaceAll('>', '&gt;');
}
function renderChat(items) {
    chatHistory.innerHTML = '';
    for (const m of items) {
        const row = document.createElement('div');
        row.style.margin = '.15rem 0';
        row.innerHTML = `<span class="pill" style="margin-right:.35rem">${m.ts || ''}</span><strong>${escapeHtml(m.user)}</strong>: ${escapeHtml(m.text)}`;
        chatHistory.appendChild(row);
    }
    chatHistory.scrollTop = chatHistory.scrollHeight;
}
chatInput.addEventListener('keydown', (e) => {
    if (e.key === 'Enter') {
        e.preventDefault();
        sendChat();
    }
});
async function sendChat() {
    const { base, token } = cfg();
    const v = (chatInput.value || '').trim();
    if (!v) {
        setLog('Type a message first');
        return;
    }
    try {
        const res = await fetch(`${base}/chat`, { method: 'POST', headers: { 'Authorization': `Bearer ${token}`, 'Content-Type': 'application/json' }, body: JSON.stringify({ message: v }) });
        const raw = await res.text();
        let parsed = null;
        try {
            parsed = JSON.parse(raw);
        }
        catch { }
        const bodyForLog = isLikelyHtml(raw, res.headers.get('content-type') || '') ? '[HTML response omitted]' : raw;
        const pretty = parsed ? JSON.stringify(parsed, null, 2) : bodyForLog;
        if (!res.ok) {
            const msg = (parsed && (parsed.detail || parsed.message)) || `${res.status} ${res.statusText}`;
            toast(msg, 'error');
            setLog(`${res.status} ${res.statusText}\n${pretty}`);
            return;
        }
        toast('Message sent', 'success');
        setLog(`${res.status} ${res.statusText}\n${pretty}`);
        chatInput.value = '';
        loadChat();
    }
    catch (e) {
        setLog('Error: ' + e);
        toast(String(e), 'error');
    }
}
// expose minimal API for buttons
window.app = { doCall, sendChat };
// initial loads and polling
doCall('status');
loadChat();
setInterval(loadChat, 4000);
setInterval(() => doCall('status'), 10000);
export {};
