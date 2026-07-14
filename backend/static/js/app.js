/**
 * app.js — Main application controller.
 * Handles routing, auth (login + register), tab switching.
 */

const App = {
    token: null,

    init() {
        this.token = localStorage.getItem('srs_token');
        this.views = document.querySelectorAll('.view');

        // Form submit bindings
        document.getElementById('login-form').addEventListener('submit', (e) => { e.preventDefault(); this.login(); });
        document.getElementById('register-form').addEventListener('submit', (e) => { e.preventDefault(); this.register(); });
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
        const hash = window.location.hash;

        if (hash === '#manager') {
            this.showView('manager-view');
            Manager.init();
            return;
        }

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

    // ── Tab Switching ──
    showTab(tab) {
        const loginForm = document.getElementById('login-form');
        const registerForm = document.getElementById('register-form');
        const tabLogin = document.getElementById('tab-login');
        const tabRegister = document.getElementById('tab-register');
        const tabsEl = document.querySelector('.auth-tabs');

        if (tab === 'login') {
            loginForm.classList.add('active');
            registerForm.classList.remove('active');
            tabLogin.classList.add('active');
            tabLogin.setAttribute('aria-selected', 'true');
            tabRegister.classList.remove('active');
            tabRegister.setAttribute('aria-selected', 'false');
            tabsEl.classList.remove('on-register');
        } else {
            registerForm.classList.add('active');
            loginForm.classList.remove('active');
            tabRegister.classList.add('active');
            tabRegister.setAttribute('aria-selected', 'true');
            tabLogin.classList.remove('active');
            tabLogin.setAttribute('aria-selected', 'false');
            tabsEl.classList.add('on-register');
        }
        // Clear errors on tab switch
        document.getElementById('login-error').classList.add('hidden');
        document.getElementById('register-error').classList.add('hidden');
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
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ username, password }),
            });
            const data = await res.json();

            if (res.ok) {
                api.setToken(data.token);
                this.token = data.token;
                this.toast(`Welcome back, ${data.name}! 👋`, 'success');
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

    // ── Register ──
    async register() {
        const name = document.getElementById('reg-name').value.trim();
        const username = document.getElementById('reg-username').value.trim();
        const password = document.getElementById('reg-password').value;
        const confirm = document.getElementById('reg-confirm').value;
        const btn = document.getElementById('register-btn');
        const errorEl = document.getElementById('register-error');

        errorEl.classList.add('hidden');

        // Client-side validation
        if (!name || !username || !password || !confirm) {
            this._showFormError(errorEl, 'All fields except Skills are required.');
            return;
        }
        if (username.length < 3) {
            this._showFormError(errorEl, 'Username must be at least 3 characters.');
            return;
        }
        if (password.length < 6) {
            this._showFormError(errorEl, 'Password must be at least 6 characters.');
            return;
        }
        if (password !== confirm) {
            this._showFormError(errorEl, 'Passwords do not match.');
            return;
        }

        // Collect selected skills
        const skillChecks = document.querySelectorAll('#register-form .skill-chip input:checked');
        const skill_tags = Array.from(skillChecks).map(c => c.value);

        this._setLoading(btn, true);
        try {
            const res = await fetch('/api/auth/register/', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ name, username, password, skill_tags }),
            });
            const data = await res.json();

            if (res.ok || res.status === 201) {
                api.setToken(data.token);
                this.token = data.token;
                this.toast(`Account created! Welcome, ${data.name}! 🎉`, 'success');
                this.handleRouting();
            } else {
                const errors = data.errors || {};
                const msg = Object.values(errors)[0] || data.error || 'Registration failed.';
                this._showFormError(errorEl, msg);
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
        this.showTab('login');
    },

    // ── Helpers ──
    _showFormError(el, msg) {
        el.textContent = msg;
        el.classList.remove('hidden');
    },

    _setLoading(btn, loading) {
        btn.disabled = loading;
        btn.querySelector('.btn-text').style.opacity = loading ? '0' : '1';
        btn.querySelector('.btn-spinner').classList.toggle('hidden', !loading);
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

    toast(msg, type = 'info') {
        const container = document.getElementById('toast-container');
        const t = document.createElement('div');
        t.className = `toast ${type}`;
        t.textContent = msg;
        container.appendChild(t);
        setTimeout(() => t.remove(), 4000);
    },
};

window.addEventListener('DOMContentLoaded', () => App.init());
