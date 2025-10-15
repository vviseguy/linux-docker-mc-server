const logEl = document.getElementById('log');
const LOG_KEY = 'mc-console-log';
function append(text) {
    logEl.textContent = text;
}
function clear() { logEl.textContent = ''; }
async function copy() {
    try {
        await navigator.clipboard.writeText(logEl.textContent || '');
        alert('Copied');
    }
    catch {
        alert('Copy failed');
    }
}
window.logs = { append, clear, copy };
// Load a quick status to show we're connected (optional)
(async () => {
    try {
        const last = localStorage.getItem(LOG_KEY);
        if (last) {
            append(last);
        }
        else {
            append('Ready. Open the main page to trigger API calls; recent responses will not stream here automatically.');
        }
    }
    catch {
        append('Ready. Open the main page to trigger API calls; recent responses will not stream here automatically.');
    }
})();
export {};
