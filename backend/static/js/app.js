/**
 * app.js — Main application controller.
 * Handles routing, auth (login only — registration is manager-provisioned).
 */

const App = {
    token: null,

    init() {
        this.token = localStorage.getItem('srs_token');
        this.views = document.querySelectorAll('.view');

        // Form submit bindings
        document.getElementById('login-form').addEventListener('submit', (e) => { e.preventDefault(); this.login(); });
        document.getElementById('logout-btn').addEventListener('click', () => this.logout());

        window.addEventListener('hashchange', () => this.handleRouting());
        this.handleRouting();
    },

    showView(id) {
        this.views.forEach(v => v.classList.remove('active'));
        const target = document.getElementById(id);
        if (target) target.classList.add('active');

        // Show/hide header
        const header = document.getElementById('app-header');
        const authViews = ['auth-view', 'loading-view'];
        if (authViews.includes(id)) {
            header.classList.add('hidden');
        } else {
            header.classList.remove('hidden');
        }
    },

    async handleRouting() {
        if (this.token) {
            this.showView('loading-view');
            const empData = await api.get('/employees/me/');
            if (empData && !empData.error) {
                window.ws.connect(this.token);
                Employee.init(empData);
                this.showView('employee-view');
            } else {
                this.logout();
            }
        } else {
            this.showView('auth-view');
        }
    },

    // ── Login ──
    async login() {
        const username = document.getElementById('login-username').value.trim();
        const password = document.getElementById('login-password').value;
        const btn = document.getElementById('login-btn');
        const errorEl = document.getElementById('login-error');

        errorEl.classList.add('hidden');
        if (!username || !password) {
            this._showFormError(errorEl, 'Please enter your username and password.');
            return;
        }

        this._setLoading(btn, true);
        try {
            const res = await fetch('/api/auth/token/', {
                method: 'POST',
                credentials: 'same-origin',
                cache: 'no-store',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ username, password }),
            });
            const data = await res.json();

            if (res.ok) {
                api.setToken(data.token);
                this.token = data.token;
                this.showToast(`Welcome back, ${data.name}! 👋`, 'success');
                this.handleRouting();
            } else {
                this._showFormError(errorEl, data.error || 'Login failed.');
            }
        } catch {
            this._showFormError(errorEl, 'Network error. Check your connection.');
        } finally {
            this._setLoading(btn, false);
        }
    },

    logout() {
        localStorage.removeItem('srs_token');
        api.setToken(null);
        this.token = null;
        if (window.ws && window.ws.ws) window.ws.ws.close();
        this.showView('auth-view');
    },

    // ── Helpers ──
    _showFormError(el, msg) {
        el.textContent = msg;
        el.classList.remove('hidden');
    },

    _setLoading(btn, loading) {
        btn.disabled = loading;
        const textEl = btn.querySelector('.btn-text');
        const spinEl = btn.querySelector('.btn-spinner');
        if (textEl) textEl.style.opacity = loading ? '0' : '1';
        if (spinEl) spinEl.classList.toggle('hidden', !loading);
    },

    togglePassword(inputId, btn) {
        const input = document.getElementById(inputId);
        if (input.type === 'password') {
            input.type = 'text';
            btn.title = 'Hide password';
        } else {
            input.type = 'password';
            btn.title = 'Show password';
        }
    },

    showToast(msg, type = 'info') {
        const container = document.getElementById('toast-container');
        if (!container) return;
        const t = document.createElement('div');
        t.className = `toast toast-${type}`;
        t.textContent = msg;
        container.appendChild(t);
        // Animate in
        requestAnimationFrame(() => t.classList.add('toast-visible'));
        setTimeout(() => {
            t.classList.remove('toast-visible');
            setTimeout(() => t.remove(), 400);
        }, 4000);
    },

    // Legacy alias
    toast(msg, type) { this.showToast(msg, type); },
};

window.addEventListener('DOMContentLoaded', () => App.init());
