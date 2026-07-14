const App = {
    init() {
        this.views = document.querySelectorAll('.view');
        this.token = localStorage.getItem('srs_token');
        
        this.handleRouting();
        window.addEventListener('hashchange', () => this.handleRouting());
        
        // Login bindings
        document.getElementById('login-btn').addEventListener('click', () => this.login());
    },

    showView(id) {
        this.views.forEach(v => v.classList.remove('active'));
        document.getElementById(id).classList.add('active');
    },

    async handleRouting() {
        const hash = window.location.hash;
        
        if (hash === '#manager') {
            this.showView('manager-view');
            Manager.init();
            return;
        }
        
        // Employee flow
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
            this.showView('login-view');
        }
    },

    async login() {
        const input = document.getElementById('token-input').value.trim();
        if (!input) return;
        
        document.getElementById('login-btn').disabled = true;
        try {
            const res = await fetch('/api/auth/token/', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({token: input})
            });
            const data = await res.json();
            
            if (res.ok) {
                api.setToken(data.token);
                this.token = data.token;
                this.handleRouting();
            } else {
                alert("Login failed: " + (data.error || 'Unknown error'));
            }
        } catch (e) {
            console.error(e);
            alert("Network error during login");
        } finally {
            document.getElementById('login-btn').disabled = false;
        }
    },

    logout() {
        localStorage.removeItem('srs_token');
        this.token = null;
        if (window.ws.ws) window.ws.ws.close();
        this.showView('login-view');
    }
};

window.addEventListener('DOMContentLoaded', () => App.init());
