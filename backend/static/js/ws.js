class ReconnectingWebSocket {
    constructor() {
        this.ws = null;
        this.backoff = { initial: 1000, max: 30000, multiplier: 2 };
        this.attempt = 0;
        this.messageHandlers = {};
        this.statusIndicator = document.getElementById('status-indicator');
    }
    
    connect(token) {
        if (!token) return;
        this.token = token;
        const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        this.url = `${protocol}//${window.location.host}/ws/employee/${token}/`;
        
        this._updateStatus('connecting', 'Connecting...');
        
        this.ws = new WebSocket(this.url);
        
        this.ws.onopen = () => {
            this.attempt = 0;
            this._updateStatus('online', 'Online');
        };
        
        this.ws.onclose = () => {
            this._updateStatus('offline', 'Offline');
            this.scheduleReconnect();
        };
        
        this.ws.onerror = (err) => {
            console.error("WS Error", err);
        };
        
        this.ws.onmessage = (e) => {
            try {
                const data = JSON.parse(e.data);
                this.handleMessage(data);
            } catch(err) {
                console.error("WS parse error", err);
            }
        };
    }
    
    scheduleReconnect() {
        if (!this.token) return;
        const delay = Math.min(
            this.backoff.initial * Math.pow(this.backoff.multiplier, this.attempt),
            this.backoff.max
        );
        this.attempt++;
        console.log(`Reconnecting in ${delay}ms...`);
        setTimeout(() => this.connect(this.token), delay);
    }
    
    on(type, handler) {
        this.messageHandlers[type] = handler;
    }
    
    handleMessage(data) {
        if (this.messageHandlers[data.type]) {
            this.messageHandlers[data.type](data);
        } else {
            console.log("Unhandled WS msg:", data);
        }
    }
    
    send(type, payload = {}) {
        if (!this.ws || this.ws.readyState !== WebSocket.OPEN) {
            console.warn("WS not open, queuing message in localStorage");
            this._queueOfflineWS({type, ...payload});
            return false;
        }
        this.ws.send(JSON.stringify({type, ...payload}));
        return true;
    }

    _queueOfflineWS(msg) {
        let q = JSON.parse(localStorage.getItem('ws_queue') || '[]');
        q.push(msg);
        localStorage.setItem('ws_queue', JSON.stringify(q));
    }

    drainOfflineQueue() {
        if (this.ws && this.ws.readyState === WebSocket.OPEN) {
            let q = JSON.parse(localStorage.getItem('ws_queue') || '[]');
            while (q.length > 0) {
                let msg = q.shift();
                this.ws.send(JSON.stringify(msg));
            }
            localStorage.setItem('ws_queue', '[]');
        }
    }
    
    _updateStatus(status, text) {
        const indicator = document.getElementById('status-indicator');
        const label = document.getElementById('status-label');
        if (!indicator) return;

        if (label) label.textContent = text;
        indicator.className = `status-pill status-${status}`;
        
        if (status === 'online') {
            this.drainOfflineQueue();
            if (window.api) window.api.drainQueue();
        }
    }
}

window.ws = new ReconnectingWebSocket();
