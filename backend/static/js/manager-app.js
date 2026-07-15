/**
 * manager-app.js
 * Manager portal controller handling auth, routing, and live WebSocket feeds.
 */

const MgrApp = {
    csrfToken: '',
    wsManager: null,
    wsPreview: null,
    zones: [],

    init() {
        this.checkAuth();
        
        // Setup Login Form
        const loginForm = document.getElementById('mgr-login-form');
        if (loginForm) {
            loginForm.addEventListener('submit', (e) => {
                e.preventDefault();
                this.login();
            });
        }
        
        // Setup Logout
        const logoutBtn = document.getElementById('mgr-logout-btn');
        if (logoutBtn) {
            logoutBtn.addEventListener('click', () => this.logout());
        }

        // Setup Sidebar Nav
        document.querySelectorAll('.nav-item').forEach(btn => {
            btn.addEventListener('click', (e) => {
                this.navigate(e.currentTarget.dataset.page);
            });
        });

        // Add Employee Form
        const addEmpForm = document.getElementById('form-add-emp');
        if (addEmpForm) {
            addEmpForm.addEventListener('submit', (e) => {
                e.preventDefault();
                this.addEmployee();
            });
        }

        // Preview Zone Select
        const previewSelect = document.getElementById('preview-zone-select');
        if (previewSelect) {
            previewSelect.addEventListener('change', (e) => {
                this.startPreview(e.target.value);
            });
        }
        
        // Analytics Range
        const analyticsRange = document.getElementById('analytics-range');
        if (analyticsRange) {
            analyticsRange.addEventListener('change', () => this.loadAnalytics());
        }
    },

    async checkAuth() {
        try {
            const res = await fetch('/api/auth/manager/me/', {
                credentials: 'same-origin',
            });
            if (res.ok) {
                const data = await res.json();
                this.csrfToken = data.csrftoken;
                document.getElementById('mgr-display-name').textContent = data.display_name;
                this.showApp();
            } else {
                this.showLogin();
            }
        } catch (err) {
            console.error('Auth check error', err);
            this.showLogin();
        }
    },

    async login() {
        const username = document.getElementById('mgr-username').value.trim();
        const password = document.getElementById('mgr-password').value;
        const errorEl = document.getElementById('mgr-login-error');
        const btn = document.getElementById('mgr-login-btn');

        errorEl.classList.add('hidden');
        btn.disabled = true;
        btn.textContent = 'Logging in...';

        try {
            const res = await fetch('/api/auth/manager/login/', {
                method: 'POST',
                credentials: 'same-origin',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ username, password })
            });
            const data = await res.json();
            
            if (res.ok) {
                this.csrfToken = data.csrftoken;
                document.getElementById('mgr-display-name').textContent = data.display_name;
                this.showApp();
            } else {
                errorEl.textContent = data.error || 'Login failed';
                errorEl.classList.remove('hidden');
            }
        } catch (err) {
            errorEl.textContent = 'Network error';
            errorEl.classList.remove('hidden');
        } finally {
            btn.disabled = false;
            btn.textContent = 'Login to Dashboard';
        }
    },

    async logout() {
        try {
            await fetch('/api/auth/manager/logout/', {
                method: 'POST',
                credentials: 'same-origin',
                headers: { 'X-CSRFToken': this.csrfToken }
            });
        } catch(e) {}
        
        if (this.wsManager) this.wsManager.close();
        if (this.wsPreview) this.wsPreview.close();
        
        window.location.reload();
    },

    showLogin() {
        document.getElementById('auth-view').classList.remove('hidden');
        document.getElementById('app-view').classList.add('hidden');
    },

    showApp() {
        document.getElementById('auth-view').classList.add('hidden');
        document.getElementById('app-view').classList.remove('hidden');
        
        // Init WS and load initial page
        this.connectManagerWS();
        this.loadZones();
        this.navigate('dashboard');
    },

    navigate(pageId) {
        // Update nav UI
        document.querySelectorAll('.nav-item').forEach(btn => {
            btn.classList.toggle('active', btn.dataset.page === pageId);
        });

        // Hide all pages
        document.querySelectorAll('.page-section').forEach(page => {
            page.classList.add('hidden');
        });

        // Show target page
        const target = document.getElementById(`page-${pageId}`);
        if (target) {
            target.classList.remove('hidden');
        }

        // Update Header Title
        const titles = {
            'dashboard': 'Live Dashboard',
            'roster': 'Roster Management',
            'analytics': 'Analytics & Performance',
            'preview': 'Live CV Preview'
        };
        document.getElementById('page-title').textContent = titles[pageId] || 'Dashboard';

        // Stop preview if navigating away from preview page
        if (pageId !== 'preview') {
            this.stopPreview();
        }

        // Load specific page data
        if (pageId === 'dashboard') this.loadDashboard();
        if (pageId === 'roster') this.loadRoster();
        if (pageId === 'analytics') this.loadAnalytics();
        if (pageId === 'preview') this.populatePreviewZoneSelect();
    },

    // ── WS Connections ──

    connectManagerWS() {
        const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        this.wsManager = new WebSocket(`${protocol}//${window.location.host}/ws/manager/`);
        
        this.wsManager.onmessage = (e) => {
            try {
                const data = JSON.parse(e.data);
                if (data.type === 'zone_update') {
                    this.updateZoneCard(data);
                } else if (data.type === 'employee_status_update') {
                    // Update analytics or roster tables if visible
                    this.updateEmployeeStatusUI(data);
                }
            } catch (err) {}
        };
        
        this.wsManager.onclose = () => {
            setTimeout(() => this.connectManagerWS(), 3000);
        };
    },

    // ── Data Loading & API Helpers ──

    async apiCall(url, method = 'GET', body = null) {
        const options = {
            method,
            headers: {},
            credentials: 'same-origin',
        };
        if (['POST', 'PUT', 'PATCH', 'DELETE'].includes(method)) {
            options.headers['X-CSRFToken'] = this.csrfToken;
        }
        if (body) {
            options.headers['Content-Type'] = 'application/json';
            options.body = JSON.stringify(body);
        }
        
        const res = await fetch(url, options);
        let data = null;
        if (res.status !== 204) {
            try { data = await res.json(); } catch(e){}
        }
        return { ok: res.ok, status: res.status, data };
    },

    async loadZones() {
        const res = await this.apiCall('/api/zones/');
        if (res.ok) {
            this.zones = res.data;
        }
    },

    // ── Dashboard Page ──

    async loadDashboard() {
        const res = await this.apiCall('/api/zones/status/');
        if (res.ok) {
            this.renderZonesGrid(res.data);
        }
    },

    renderZonesGrid(zones) {
        const grid = document.getElementById('zones-grid');
        grid.innerHTML = '';
        let alerts = 0;
        
        zones.forEach(z => {
            if (z.current_state === 'ALERT') alerts++;
            
            const card = document.createElement('div');
            card.className = `card ${z.current_state === 'ALERT' ? 'border-red' : ''}`;
            card.id = `zone-card-${z.id}`;
            card.innerHTML = `
                <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:16px;">
                    <h4 style="margin:0; font-size:1.1rem;">${z.name}</h4>
                    <span class="badge ${z.current_state === 'ALERT' ? 'badge-BUSY' : 'badge-FREE'}">${z.current_state}</span>
                </div>
                <div style="color:var(--text-muted); font-size:0.9rem; margin-bottom:8px;">
                    Density: <strong id="z-density-${z.id}" style="color:white;">${z.current_threshold.density || 0}</strong>
                </div>
                <div style="color:var(--text-muted); font-size:0.9rem;">
                    Active Tasks: <strong style="color:white;">${z.active_task_count}</strong>
                </div>
            `;
            grid.appendChild(card);
        });
        
        document.getElementById('stat-alert-zones').textContent = alerts;
        this.updateActiveStaffCount();
    },

    updateZoneCard(data) {
        const badge = document.querySelector(`#zone-card-${data.zone_id} .badge`);
        const density = document.getElementById(`z-density-${data.zone_id}`);
        const card = document.getElementById(`zone-card-${data.zone_id}`);
        
        if (badge) {
            badge.textContent = data.state;
            badge.className = `badge ${data.state === 'ALERT' ? 'badge-BUSY' : 'badge-FREE'}`;
        }
        if (density) {
            density.textContent = data.density.toFixed(2);
        }
        if (card) {
            if (data.state === 'ALERT') card.classList.add('border-red');
            else card.classList.remove('border-red');
        }
    },

    async updateActiveStaffCount() {
        const res = await this.apiCall('/api/employees/');
        if (res.ok) {
            const online = res.data.filter(e => e.status !== 'OFFLINE' && e.status !== 'ON_BREAK').length;
            document.getElementById('stat-active-staff').textContent = online;
        }
    },

    // ── Roster Page ──

    async loadRoster() {
        const res = await this.apiCall('/api/employees/');
        if (res.ok) {
            const tbody = document.getElementById('roster-tbody');
            tbody.innerHTML = '';
            
            res.data.forEach(emp => {
                const tr = document.createElement('tr');
                tr.id = `roster-row-${emp.id}`;
                tr.innerHTML = `
                    <td>
                        <div style="font-weight:500; color:white;">${emp.name}</div>
                        <div style="font-size:0.8rem; color:var(--text-muted);">@${emp.username}</div>
                    </td>
                    <td><span id="roster-status-${emp.id}" class="badge badge-${emp.status}">${emp.status === 'ON_BREAK' ? '☕ ON BREAK' : emp.status}</span></td>
                    <td>${emp.current_zone_name || '—'}</td>
                    <td>
                        <button class="btn-icon" style="color:var(--text-muted);" title="Remove" onclick="MgrApp.removeEmployee(${emp.id}, '${emp.name}')">
                            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M3 6h18"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/><line x1="10" y1="11" x2="10" y2="17"/><line x1="14" y1="11" x2="14" y2="17"/></svg>
                        </button>
                    </td>
                `;
                tbody.appendChild(tr);
            });
        }
    },

    showAddEmployeeModal() {
        document.getElementById('modal-add-emp').classList.add('active');
        document.getElementById('form-add-emp').reset();
    },

    closeModal(id) {
        document.getElementById(id).classList.remove('active');
    },

    async addEmployee() {
        const name = document.getElementById('add-emp-name').value.trim();
        const username = document.getElementById('add-emp-username').value.trim();
        const password = document.getElementById('add-emp-password').value;
        const skillsRaw = document.getElementById('add-emp-skills').value;
        const skills = skillsRaw.split(',').map(s => s.trim()).filter(s => s);

        if (!name) {
            this.showToast('Employee name is required.', 'error');
            return;
        }
        if (!username) {
            this.showToast('Username is required for employee login.', 'error');
            return;
        }
        if (!password) {
            this.showToast('Password is required for employee login.', 'error');
            return;
        }

        const payload = {
            name: name,
            username: username,
            password: password,
            skill_tags: skills,
        };
        if (username) payload.username = username;

        const res = await this.apiCall('/api/employees/', 'POST', payload);

        if (res.ok) {
            this.closeModal('modal-add-emp');
            document.getElementById('result-title').textContent = 'Employee Created';
            document.getElementById('result-message').textContent = `Employee ${res.data.username} created successfully.`;
            document.getElementById('modal-result').classList.add('active');
        } else {
            this.showToast('Failed to add employee: ' + (res.data?.error || 'Unknown error'), 'error');
        }
    },

    async removeEmployee(id, name, force = false) {
        if (!force && !confirm(`Remove employee ${name}?`)) return;

        const url = `/api/employees/${id}/${force ? '?force=true' : ''}`;
        const res = await this.apiCall(url, 'DELETE');

        if (res.ok) {
            this.showToast(`${name} removed successfully.`, 'success');
            this.loadRoster();
        } else if (res.status === 409) {
            // Has active task
            if (confirm(`${name} has an active task (${res.data.task_status} in ${res.data.zone}).\n\nForce remove and cancel this task?`)) {
                this.removeEmployee(id, name, true);
            }
        } else {
            this.showToast('Failed to remove: ' + (res.data?.error || 'Unknown error'), 'error');
        }
    },

    // ── Analytics Page ──

    async loadAnalytics() {
        const range = document.getElementById('analytics-range').value;
        const res = await this.apiCall(`/api/dashboard/employee_stats?range=${range}`);
        
        if (res.ok) {
            const tbody = document.getElementById('analytics-tbody');
            tbody.innerHTML = '';
            
            res.data.employees.forEach(emp => {
                const tr = document.createElement('tr');
                const ratePct = emp.ack_rate !== null ? Math.round(emp.ack_rate * 100) : 0;
                
                let breakHtml = '—';
                if (emp.status === 'ON_BREAK') {
                    breakHtml = `<span class="badge badge-ON_BREAK">☕ Until ${new Date(emp.break_ends_at).toLocaleTimeString([], {hour:'2-digit', minute:'2-digit'})}</span>`;
                }

                tr.innerHTML = `
                    <td style="font-weight:500; color:white;">${emp.name}</td>
                    <td id="analytics-break-${emp.employee_id}">${breakHtml}</td>
                    <td style="color:#10b981; font-weight:600;">${emp.acknowledged}</td>
                    <td style="color:#ef4444; font-weight:600;">${emp.missed}</td>
                    <td>
                        <div style="display:flex; align-items:center; gap:12px;">
                            <div class="progress-bar-bg" style="width: 100px;">
                                <div class="progress-bar-fill" style="width: ${ratePct}%; background: ${ratePct < 50 && emp.missed > 0 ? '#ef4444' : 'var(--accent-primary)'};"></div>
                            </div>
                            <span style="font-size:0.85rem; color:var(--text-muted);">${emp.ack_rate !== null ? ratePct+'%' : 'N/A'}</span>
                        </div>
                    </td>
                `;
                tbody.appendChild(tr);
            });
        }
    },

    updateEmployeeStatusUI(data) {
        // Update roster badge if exists
        const rBadge = document.getElementById(`roster-status-${data.employee_id}`);
        if (rBadge) {
            rBadge.textContent = data.status === 'ON_BREAK' ? '☕ ON BREAK' : data.status;
            rBadge.className = `badge badge-${data.status}`;
        }
        
        // Update analytics break column if exists
        const aBreak = document.getElementById(`analytics-break-${data.employee_id}`);
        if (aBreak) {
            if (data.status === 'ON_BREAK' && data.break_ends_at) {
                aBreak.innerHTML = `<span class="badge badge-ON_BREAK">☕ Until ${new Date(data.break_ends_at).toLocaleTimeString([], {hour:'2-digit', minute:'2-digit'})}</span>`;
            } else {
                aBreak.innerHTML = '—';
            }
        }
    },

    // ── Preview Page ──

    populatePreviewZoneSelect() {
        const select = document.getElementById('preview-zone-select');
        select.innerHTML = '<option value="">— Select a Zone —</option>';
        this.zones.forEach(z => {
            const opt = document.createElement('option');
            opt.value = z.id;
            opt.textContent = z.name;
            select.appendChild(opt);
        });
    },

    startPreview(zoneId) {
        this.stopPreview();
        if (!zoneId) {
            document.getElementById('preview-placeholder').classList.remove('hidden');
            document.getElementById('preview-img').classList.add('hidden');
            document.getElementById('preview-status').classList.add('hidden');
            return;
        }

        document.getElementById('preview-placeholder').classList.add('hidden');
        document.getElementById('preview-img').classList.remove('hidden');
        document.getElementById('preview-status').classList.remove('hidden');
        document.getElementById('preview-fps').textContent = 'Connecting...';

        const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        this.wsPreview = new WebSocket(`${protocol}//${window.location.host}/ws/manager/preview/${zoneId}/`);
        
        let framesReceived = 0;
        let lastFpsTime = Date.now();

        this.wsPreview.onmessage = (e) => {
            try {
                const data = JSON.parse(e.data);
                if (data.type === 'preview_frame') {
                    // Update image source with base64 JPEG
                    document.getElementById('preview-img').src = `data:image/jpeg;base64,${data.frame}`;
                    
                    // Simple FPS calculation
                    framesReceived++;
                    const now = Date.now();
                    if (now - lastFpsTime >= 2000) { // Update every 2s
                        const fps = (framesReceived / ((now - lastFpsTime) / 1000)).toFixed(1);
                        document.getElementById('preview-fps').textContent = `${fps} FPS`;
                        framesReceived = 0;
                        lastFpsTime = now;
                    }
                }
            } catch (err) {}
        };
        
        this.wsPreview.onclose = () => {
            document.getElementById('preview-fps').textContent = 'Disconnected';
        };
    },

    stopPreview() {
        if (this.wsPreview) {
            this.wsPreview.close();
            this.wsPreview = null;
        }
    },

    showToast(msg, type = 'info') {
        const container = document.getElementById('toast-container');
        if (!container) return;
        const t = document.createElement('div');
        t.className = `toast toast-${type}`;
        t.textContent = msg;
        container.appendChild(t);
        requestAnimationFrame(() => t.classList.add('toast-visible'));
        setTimeout(() => {
            t.classList.remove('toast-visible');
            setTimeout(() => t.remove(), 400);
        }, 4000);
    }
};

window.addEventListener('DOMContentLoaded', () => MgrApp.init());
