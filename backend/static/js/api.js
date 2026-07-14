class API {
    constructor() {
        this.baseUrl = '/api';
        this.token = localStorage.getItem('srs_token');
        this.initDB();
        
        window.addEventListener('online', () => this.drainQueue());
    }

    async initDB() {
        this.db = await idb.openDB('srs-db', 1, {
            upgrade(db) {
                db.createObjectStore('api-queue', { keyPath: 'id', autoIncrement: true });
            }
        });
    }

    setToken(token) {
        this.token = token;
        localStorage.setItem('srs_token', token);
    }

    async get(path) {
        try {
            const res = await fetch(`${this.baseUrl}${path}`, {
                headers: { 'Authorization': `Token ${this.token}` }
            });
            if (!res.ok) throw new Error(`HTTP ${res.status}`);
            return await res.json();
        } catch (err) {
            console.error("API GET Error:", err);
            return null; // Will fallback to SW cache if offline
        }
    }

    async post(path, data = {}) {
        return this._queueableRequest('POST', path, data);
    }

    async patch(path, data = {}) {
        return this._queueableRequest('PATCH', path, data);
    }

    async _queueableRequest(method, path, data) {
        if (!navigator.onLine) {
            await this.enqueue(method, path, data);
            return { queued: true };
        }

        try {
            const res = await fetch(`${this.baseUrl}${path}`, {
                method,
                headers: { 
                    'Content-Type': 'application/json',
                    'Authorization': `Token ${this.token}`
                },
                body: JSON.stringify(data)
            });
            if (!res.ok) throw new Error(`HTTP ${res.status}`);
            return await res.json();
        } catch (err) {
            console.warn("Request failed, queueing for offline retry", err);
            await this.enqueue(method, path, data);
            return { queued: true };
        }
    }

    async enqueue(method, path, data) {
        if (!this.db) await this.initDB();
        await this.db.add('api-queue', { method, path, data, timestamp: Date.now() });
        
        // Try to register background sync if supported
        if ('serviceWorker' in navigator && 'SyncManager' in window) {
            try {
                const swReg = await navigator.serviceWorker.ready;
                await swReg.sync.register('sync-api');
            } catch (e) { /* ignore */ }
        }
    }

    async drainQueue() {
        if (!this.db || !navigator.onLine) return;
        const tx = this.db.transaction('api-queue', 'readwrite');
        const store = tx.objectStore('api-queue');
        const requests = await store.getAll();

        for (let req of requests) {
            try {
                const res = await fetch(`${this.baseUrl}${req.path}`, {
                    method: req.method,
                    headers: { 
                        'Content-Type': 'application/json',
                        'Authorization': `Token ${this.token}`
                    },
                    body: JSON.stringify(req.data)
                });
                if (res.ok) {
                    await store.delete(req.id);
                }
            } catch (err) {
                console.error("Drain queue failed", err);
                break; // Stop draining if network fails again
            }
        }
    }
}

window.api = new API();
