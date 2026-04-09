const BACKEND_URL = 'https://nse-csv-api.onrender.com'; // Change to your backend URL after deploy

class Dashboard {
    constructor() {
        this.runTimeInput = document.getElementById('runTime');
        this.enabledToggle = document.getElementById('enabledToggle');
        this.settingsForm = document.getElementById('settingsForm');
        this.runNowBtn = document.getElementById('runNowBtn');
        this.backendStatus = document.getElementById('backendStatus');
        
        this.init();
    }

    async init() {
        this.setupEventListeners();
        await this.loadSettings();
        await this.checkBackendStatus();
        await this.loadLogs();
        
        // Auto-refresh every 30 seconds
        setInterval(() => this.refreshData(), 30000);
    }

    setupEventListeners() {
        this.settingsForm.addEventListener('submit', (e) => this.handleSaveSettings(e));
        this.runNowBtn.addEventListener('click', () => this.handleRunNow());
    }

    async handleSaveSettings(e) {
        e.preventDefault();
        const time = this.runTimeInput.value;
        const enabled = this.enabledToggle.checked;

        if (!time) {
            this.showStatus('settingsStatus', 'Please select a time', 'error');
            return;
        }

        try {
            const response = await fetch(`${BACKEND_URL}/api/settings`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ run_time: time, enabled })
            });

            const data = await response.json();
            if (response.ok) {
                this.showStatus('settingsStatus', '✅ Settings saved successfully!', 'success');
                await this.loadSettings();
            } else {
                this.showStatus('settingsStatus', `❌ Error: ${data.detail || 'Unknown error'}`, 'error');
            }
        } catch (err) {
            this.showStatus('settingsStatus', `❌ Connection error: ${err.message}`, 'error');
        }
    }

    async handleRunNow() {
        this.runNowBtn.disabled = true;
        this.showStatus('runNowStatus', '⏳ Running job...', 'info');

        try {
            const response = await fetch(`${BACKEND_URL}/api/run-now`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' }
            });

            const data = await response.json();
            if (response.ok) {
                this.showStatus('runNowStatus', '✅ CSV downloaded and sent to Telegram!', 'success');
                setTimeout(() => this.loadLogs(), 2000);
            } else {
                this.showStatus('runNowStatus', `❌ Error: ${data.detail || 'Unknown error'}`, 'error');
            }
        } catch (err) {
            this.showStatus('runNowStatus', `❌ Connection error: ${err.message}`, 'error');
        } finally {
            this.runNowBtn.disabled = false;
        }
    }

    async loadSettings() {
        try {
            const response = await fetch(`${BACKEND_URL}/api/settings`);
            const data = await response.json();
            
            this.runTimeInput.value = data.run_time;
            this.enabledToggle.checked = data.enabled;
            
            if (data.next_run) {
                document.getElementById('nextRunTime').textContent = 
                    new Date(data.next_run).toLocaleString();
            }
        } catch (err) {
            console.error('Failed to load settings:', err);
        }
    }

    async loadLogs() {
        try {
            const response = await fetch(`${BACKEND_URL}/api/logs`);
            const logs = await response.json();
            this.renderLogs(logs);
        } catch (err) {
            console.error('Failed to load logs:', err);
        }
    }

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
            const date = new Date(log.created_at).toLocaleString();
            const statusClass = log.status === 'success' ? 'status-success' : 'status-failed';
            html += `
                <tr>
                    <td>${date}</td>
                    <td>${log.run_type}</td>
                    <td><span class="status-badge ${statusClass}">${log.status}</span></td>
                    <td>${log.message}</td>
                </tr>
            `;
        });

        html += '</tbody></table>';
        container.innerHTML = html;
    }

    async checkBackendStatus() {
        try {
            const response = await fetch(`${BACKEND_URL}/health`);
            if (response.ok) {
                this.backendStatus.textContent = 'Online';
                this.backendStatus.className = 'status-badge online';
            } else {
                this.setOffline();
            }
        } catch (err) {
            this.setOffline();
        }
    }

    setOffline() {
        this.backendStatus.textContent = 'Offline';
        this.backendStatus.className = 'status-badge offline';
    }

    showStatus(elementId, message, type) {
        const el = document.getElementById(elementId);
        el.textContent = message;
        el.className = `status-message show ${type}`;
    }

    async refreshData() {
        await this.loadSettings();
        await this.checkBackendStatus();
        await this.loadLogs();
    }
}

// Initialize when DOM loads
document.addEventListener('DOMContentLoaded', () => {
    new Dashboard();
});
