// ── Config keys stored in localStorage ──────────────────────────────────────
const LS_URL = 'nse_backend_url';
const LS_KEY = 'nse_api_key';

// ── HTML escape helper ────────────────────────────────────────────────────────
function escapeHtml(str) {
    return String(str)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#39;');
}

// ── Helpers ──────────────────────────────────────────────────────────────────
function getConfig() {
    return {
        url: (localStorage.getItem(LS_URL) || '').replace(/\/$/, ''),
        key: localStorage.getItem(LS_KEY) || ''
    };
}

function saveConfig(url, key) {
    localStorage.setItem(LS_URL, url.replace(/\/$/, ''));
    localStorage.setItem(LS_KEY, key);
}

function buildHeaders() {
    const { key } = getConfig();
    const h = { 'Content-Type': 'application/json' };
    if (key) h['X-API-Key'] = key;
    return h;
}

function apiUrl(path) {
    return `${getConfig().url}${path}`;
}

// ── Setup Modal ───────────────────────────────────────────────────────────────
const setupModal   = document.getElementById('setupModal');
const mainContent  = document.getElementById('mainContent');
const setupSaveBtn = document.getElementById('setupSaveBtn');
const setupError   = document.getElementById('setupError');

function showSetup() {
    const { url, key } = getConfig();
    document.getElementById('setupUrl').value = url;
    document.getElementById('setupKey').value = key;
    setupError.style.display = 'none';
    setupModal.style.display  = 'flex';
    mainContent.style.display = 'none';
}

function hideSetup() {
    setupModal.style.display  = 'none';
    mainContent.style.display = 'block';
}

setupSaveBtn.addEventListener('click', async () => {
    const url = document.getElementById('setupUrl').value.trim();
    const key = document.getElementById('setupKey').value.trim();

    if (!url) {
        setupError.textContent = 'Please enter the backend URL.';
        setupError.style.display = 'block';
        return;
    }

    // Quick health-check with the provided credentials
    setupSaveBtn.disabled = true;
    setupSaveBtn.textContent = 'Connecting…';
    try {
        const headers = {};
        if (key) headers['X-API-Key'] = key;
        const resp = await fetch(`${url.replace(/\/$/, '')}/health`, { headers });
        if (!resp.ok) throw new Error(`Status ${resp.status}`);
        saveConfig(url, key);
        hideSetup();
        dashboard.init();
    } catch (err) {
        setupError.textContent = `❌ Could not reach backend: ${err.message}`;
        setupError.style.display = 'block';
    } finally {
        setupSaveBtn.disabled = false;
        setupSaveBtn.textContent = '💾 Save & Connect';
    }
});

document.getElementById('changeConfigBtn').addEventListener('click', showSetup);

// ── Dashboard ─────────────────────────────────────────────────────────────────
const dashboard = {
    refreshTimer: null,

    init() {
        this.loadSettings();
        this.checkBackendStatus();
        this.loadLogs();
        clearInterval(this.refreshTimer);
        this.refreshTimer = setInterval(() => this.refreshData(), 30000);
    },

    setupEventListeners() {
        document.getElementById('settingsForm')
            .addEventListener('submit', (e) => this.handleSaveSettings(e));
        document.getElementById('runNowBtn')
            .addEventListener('click', () => this.handleRunNow());
    },

    async handleSaveSettings(e) {
        e.preventDefault();
        const time    = document.getElementById('runTime').value;
        const enabled = document.getElementById('enabledToggle').checked;

        if (!time) {
            this.showStatus('settingsStatus', 'Please select a time', 'error');
            return;
        }

        try {
            const response = await fetch(apiUrl('/api/settings'), {
                method: 'POST',
                headers: buildHeaders(),
                body: JSON.stringify({ run_time: time, enabled, timezone: 'Asia/Kolkata' })
            });

            const data = await response.json();
            if (response.ok) {
                this.showStatus('settingsStatus', '✅ Settings saved successfully!', 'success');
                this.updateNextRun(data.next_run);
            } else if (response.status === 401) {
                this.showStatus('settingsStatus', '❌ Invalid API key — click ⚙️ Config to update.', 'error');
            } else {
                this.showStatus('settingsStatus', `❌ Error: ${data.detail || 'Unknown error'}`, 'error');
            }
        } catch (err) {
            this.showStatus('settingsStatus', `❌ Connection error: ${err.message}`, 'error');
        }
    },

    async handleRunNow() {
        const btn = document.getElementById('runNowBtn');
        btn.disabled = true;
        this.showStatus('runNowStatus', '⏳ Running job — please wait…', 'info');

        try {
            const response = await fetch(apiUrl('/api/run-now'), {
                method: 'POST',
                headers: buildHeaders()
            });

            const data = await response.json();
            if (response.ok) {
                this.showStatus('runNowStatus', '✅ CSV downloaded and sent to Telegram!', 'success');
                setTimeout(() => this.loadLogs(), 2000);
            } else if (response.status === 401) {
                this.showStatus('runNowStatus', '❌ Invalid API key — click ⚙️ Config to update.', 'error');
            } else {
                this.showStatus('runNowStatus', `❌ Error: ${data.detail || 'Unknown error'}`, 'error');
            }
        } catch (err) {
            this.showStatus('runNowStatus', `❌ Connection error: ${err.message}`, 'error');
        } finally {
            btn.disabled = false;
        }
    },

    async loadSettings() {
        try {
            const response = await fetch(apiUrl('/api/settings'), { headers: buildHeaders() });
            if (!response.ok) return;
            const data = await response.json();

            document.getElementById('runTime').value         = data.run_time || '09:30';
            document.getElementById('enabledToggle').checked = data.enabled !== false;
            this.updateNextRun(data.next_run);
        } catch (err) {
            console.error('Failed to load settings:', err);
        }
    },

    updateNextRun(nextRun) {
        const el = document.getElementById('nextRunTime');
        if (nextRun) {
            el.textContent = new Date(nextRun).toLocaleString();
        } else {
            el.textContent = 'Disabled / Not scheduled';
        }
    },

    async loadLogs() {
        try {
            const response = await fetch(apiUrl('/api/logs'), { headers: buildHeaders() });
            if (!response.ok) return;
            const logs = await response.json();
            this.renderLogs(logs);
        } catch (err) {
            console.error('Failed to load logs:', err);
        }
    },

    renderLogs(logs) {
        const container = document.getElementById('logsContainer');

        if (!logs || logs.length === 0) {
            container.innerHTML = '<p class="loading">No logs yet</p>';
            return;
        }

        let html = `
            <table>
                <thead>
                    <tr>
                        <th>Time (UTC)</th>
                        <th>Type</th>
                        <th>Status</th>
                        <th>Message</th>
                    </tr>
                </thead>
                <tbody>
        `;

        logs.forEach(log => {
            const date        = log.created_at ? new Date(log.created_at).toLocaleString() : '—';
            const statusClass = log.status === 'success' ? 'status-success' : 'status-failed';
            const msg         = log.message ? escapeHtml(log.message) : '';
            const runType     = escapeHtml(log.run_type || '');
            const status      = escapeHtml(log.status || '');
            html += `
                <tr>
                    <td>${date}</td>
                    <td>${runType}</td>
                    <td><span class="status-badge ${statusClass}">${status}</span></td>
                    <td>${msg}</td>
                </tr>
            `;
        });

        html += '</tbody></table>';
        container.innerHTML = html;
    },

    async checkBackendStatus() {
        const badge = document.getElementById('backendStatus');
        try {
            const response = await fetch(apiUrl('/health'));
            if (response.ok) {
                badge.textContent = 'Online';
                badge.className   = 'status-badge online';
            } else {
                this.setOffline(badge);
            }
        } catch (err) {
            this.setOffline(badge);
        }
    },

    setOffline(badge) {
        badge.textContent = 'Offline';
        badge.className   = 'status-badge offline';
    },

    showStatus(elementId, message, type) {
        const el      = document.getElementById(elementId);
        el.textContent = message;
        el.className   = `status-message show ${type}`;
    },

    async refreshData() {
        await this.loadSettings();
        await this.checkBackendStatus();
        await this.loadLogs();
    }
};

// ── Bootstrap ─────────────────────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
    dashboard.setupEventListeners();

    const { url } = getConfig();
    if (!url) {
        showSetup();
    } else {
        hideSetup();
        dashboard.init();
    }
});

