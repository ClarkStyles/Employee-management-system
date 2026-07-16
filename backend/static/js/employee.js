const Employee = {
    timerInterval: null,
    activeTaskTimer: null,
    breakTimerInterval: null,
    taskExpiryTime: 0,
    taskStartTime: 0,
    breakEndsAt: null,
    breakTotalSeconds: 0,
    taskRefreshInterval: null,

    async init(data) {
        this.data = data;
        document.getElementById('emp-name').textContent = data.name;
        const initial = data.first_letter || data.name.charAt(0).toUpperCase();
        document.getElementById('emp-avatar').textContent = initial;
        this.updateBadge(data.status);

        await this.loadZones();

        // Setup WS listeners
        ws.on('task_offer', (msg) => this.handleTaskOffer(msg));
        ws.on('task_reassigned', () => this.handleTaskReassigned());
        ws.on('status_update', (msg) => this.handleStatusUpdate(msg));
        ws.on('employee_status_update', (msg) => this.onStatusUpdate(msg));

        // Setup UI bindings
        document.getElementById('zone-select').addEventListener('change', (e) => this.checkin(e.target.value));
        document.getElementById('ack-btn').addEventListener('click', () => this.ackTask());
        document.getElementById('complete-btn').addEventListener('click', () => this.completeTask());

        // If already on break from previous session, restore countdown
        if (data.status === 'ON_BREAK' && data.break_ends_at) {
            this.startBreakCountdown(data.break_ends_at);
        }

        // Show/hide break controls based on initial status
        this.syncBreakUI(data.status);

        // Check if already assigned
        this.checkExistingTask();
        this.startTaskPolling();
    },

    async loadZones() {
        const zones = await api.get('/zones/');
        const select = document.getElementById('zone-select');
        select.innerHTML = '<option value="">-- Not Checked In --</option>';
        if (zones && zones.length) {
            zones.forEach(z => {
                const opt = document.createElement('option');
                opt.value = z.id;
                opt.textContent = z.name;
                select.appendChild(opt);
            });
            if (this.data.current_zone) {
                select.value = this.data.current_zone;
            }
        }
    },

    updateBadge(status) {
        const badge = document.getElementById('emp-status-badge');
        if (!badge) return;
        const labels = {
            FREE: 'FREE',
            ASSIGNED: 'ASSIGNED',
            ACKNOWLEDGED: 'ACKNOWLEDGED',
            IN_PROGRESS: 'IN PROGRESS',
            ON_BREAK: '☕ ON BREAK',
            BUSY: 'BUSY',
            OFFLINE: 'OFFLINE',
        };
        badge.textContent = labels[status] || status;
        badge.className = `badge badge-${status}`;
        this.data.status = status;
    },

    syncBreakUI(status) {
        const breakControls = document.getElementById('break-controls-card');
        const breakCountdown = document.getElementById('break-countdown-card');
        if (!breakControls || !breakCountdown) return;

        if (status === 'ON_BREAK') {
            breakControls.classList.add('hidden');
            breakCountdown.classList.remove('hidden');
        } else if (status === 'FREE') {
            breakControls.classList.remove('hidden');
            breakCountdown.classList.add('hidden');
        } else {
            // ASSIGNED, IN_PROGRESS, etc — hide both
            breakControls.classList.add('hidden');
            breakCountdown.classList.add('hidden');
        }
    },

    async checkExistingTask() {
        await this.refreshTaskState();
    },

    startTaskPolling() {
        if (this.taskRefreshInterval) clearInterval(this.taskRefreshInterval);
        this.taskRefreshInterval = setInterval(() => this.refreshTaskState(), 5000);
    },

    stopTaskPolling() {
        if (this.taskRefreshInterval) {
            clearInterval(this.taskRefreshInterval);
            this.taskRefreshInterval = null;
        }
    },

    async refreshTaskState() {
        const tasks = await api.get('/tasks/active/');
        if (!tasks || !tasks.length) {
            this.hideOfferCard();
            this.hideActiveTask();
            return;
        }

        const myTask = tasks.find(t => t.assigned_employee === this.data.id);
        if (!myTask) {
            this.hideOfferCard();
            this.hideActiveTask();
            return;
        }

        this.currentTaskId = myTask.id;
        if (myTask.status === 'ASSIGNED') {
            const ACK_TIMEOUT = 45;
            const createdAt = new Date(myTask.created_at).getTime();
            const elapsed = Math.floor((Date.now() - createdAt) / 1000);
            const remaining = Math.max(0, ACK_TIMEOUT - elapsed);
            if (remaining > 0) {
                this.showOfferCard(myTask.zone_name, remaining);
            } else {
                this.currentTaskId = null;
                this.hideOfferCard();
            }
        } else if (myTask.status === 'ACKNOWLEDGED' || myTask.status === 'IN_PROGRESS') {
            const startTime = myTask.acknowledged_at
                ? new Date(myTask.acknowledged_at)
                : new Date(myTask.created_at);
            this.showActiveTask(myTask.zone_name, startTime);
        } else {
            this.hideOfferCard();
            this.hideActiveTask();
        }
    },

    checkin(zoneId) {
        if (!zoneId) return;
        ws.send('checkin', {zone_id: zoneId});
    },

    // ── Break Management ──────────────────────────────────────────

    startBreak(durationSeconds) {
        if (this.data.status !== 'FREE') {
            App.showToast('Cannot start break — not FREE', 'error');
            return;
        }
        ws.send('start_break', { duration_seconds: durationSeconds });
        this.breakTotalSeconds = durationSeconds;
    },

    endBreakEarly() {
        ws.send('end_break_early');
    },

    startBreakCountdown(breakEndsAtISO) {
        this.breakEndsAt = new Date(breakEndsAtISO);

        // Compute original total from current status_update vs now
        const nowMs = Date.now();
        const endsMs = this.breakEndsAt.getTime();
        const remaining = Math.max(0, endsMs - nowMs);
        if (!this.breakTotalSeconds || this.breakTotalSeconds <= 0) {
            // Guess from remaining (might be mid-break on reconnect)
            this.breakTotalSeconds = remaining / 1000;
        }

        if (this.breakTimerInterval) clearInterval(this.breakTimerInterval);

        const tick = () => {
            const rem = Math.max(0, Math.ceil((this.breakEndsAt.getTime() - Date.now()) / 1000));
            const m = Math.floor(rem / 60);
            const s = String(rem % 60).padStart(2, '0');
            const el = document.getElementById('break-timer-value');
            const fill = document.getElementById('break-progress-fill');
            if (el) el.textContent = `${m}:${s}`;

            const pct = this.breakTotalSeconds > 0
                ? Math.max(0, (rem / this.breakTotalSeconds) * 100)
                : 0;
            if (fill) fill.style.width = `${pct}%`;

            if (rem <= 0) {
                clearInterval(this.breakTimerInterval);
                // Server will broadcast break expiry; update UI immediately as well
                this.onStatusUpdate({ status: 'FREE', break_ends_at: null });
            }
        };

        tick();
        this.breakTimerInterval = setInterval(tick, 1000);
    },

    stopBreakCountdown() {
        if (this.breakTimerInterval) {
            clearInterval(this.breakTimerInterval);
            this.breakTimerInterval = null;
        }
        this.breakEndsAt = null;
        const fill = document.getElementById('break-progress-fill');
        if (fill) fill.style.width = '100%';
    },

    // Called when server sends employee_status_update (from break expiry or end_break_early)
    onStatusUpdate(data) {
        const newStatus = data.status;
        this.updateBadge(newStatus);
        this.syncBreakUI(newStatus);

        if (newStatus === 'ON_BREAK' && data.break_ends_at) {
            this.startBreakCountdown(data.break_ends_at);
        } else if (newStatus === 'FREE') {
            this.stopBreakCountdown();
            App.showToast('Break ended — welcome back! ☀️', 'success');
        }
    },

    // ── Task Management ───────────────────────────────────────────

    handleTaskOffer(msg) {
        this.currentTaskId = msg.task_id;
        this.showOfferCard(msg.zone, msg.expires_in);
    },

    showOfferCard(zoneName, expiresIn) {
        document.getElementById('offer-zone-name').textContent = zoneName;
        document.getElementById('task-offer-card').classList.remove('hidden');

        this.taskExpiryTime = Date.now() + (expiresIn * 1000);

        if (this.timerInterval) clearInterval(this.timerInterval);
        this.timerInterval = setInterval(() => {
            const remaining = Math.max(0, Math.ceil((this.taskExpiryTime - Date.now()) / 1000));
            document.getElementById('offer-timer').textContent = remaining;
            if (remaining <= 0) {
                clearInterval(this.timerInterval);
                this.hideOfferCard();
            }
        }, 1000);
    },

    hideOfferCard() {
        document.getElementById('task-offer-card').classList.add('hidden');
        if (this.timerInterval) clearInterval(this.timerInterval);
    },

    ackTask() {
        if (!this.currentTaskId) return;
        const sent = ws.send('ack', {task_id: this.currentTaskId});
        if (!sent) {
            this.hideOfferCard();
            this.showActiveTask(document.getElementById('offer-zone-name').textContent, new Date());
            document.getElementById('active-task-panel').classList.add('offline-queued');
        }
    },

    completeTask() {
        if (!this.currentTaskId) return;
        ws.send('complete', {task_id: this.currentTaskId});
        this.hideActiveTask();
        this.updateBadge('FREE');
        this.syncBreakUI('FREE');
    },

    showActiveTask(zoneName, startTime) {
        this.hideOfferCard();
        document.getElementById('active-zone-name').textContent = zoneName;
        document.getElementById('active-task-panel').classList.remove('hidden');
        document.getElementById('active-task-panel').classList.remove('offline-queued');

        this.taskStartTime = startTime.getTime();

        if (this.activeTaskTimer) clearInterval(this.activeTaskTimer);
        this.activeTaskTimer = setInterval(() => {
            const elapsed = Math.floor((Date.now() - this.taskStartTime) / 1000);
            const m = String(Math.floor(elapsed / 60)).padStart(2, '0');
            const s = String(elapsed % 60).padStart(2, '0');
            document.getElementById('active-timer').textContent = `${m}:${s}`;
        }, 1000);

        this.updateBadge('IN_PROGRESS');
        this.syncBreakUI('IN_PROGRESS');
    },

    hideActiveTask() {
        document.getElementById('active-task-panel').classList.add('hidden');
        if (this.activeTaskTimer) clearInterval(this.activeTaskTimer);
        this.currentTaskId = null;
    },

    handleTaskReassigned() {
        this.hideOfferCard();
        this.updateBadge('FREE');
        this.syncBreakUI('FREE');
        App.showToast('Task reassigned — you are FREE', 'info');
    },

    handleStatusUpdate(msg) {
        if (msg.status === 'ack_result' && msg.success) {
            document.getElementById('active-task-panel').classList.remove('offline-queued');
            if (document.getElementById('active-task-panel').classList.contains('hidden')) {
                this.showActiveTask(document.getElementById('offer-zone-name').textContent, new Date());
            }
        } else if (msg.status === 'break_started' && msg.success) {
            this.updateBadge('ON_BREAK');
            this.syncBreakUI('ON_BREAK');
            if (msg.break_ends_at) this.startBreakCountdown(msg.break_ends_at);
        } else if (msg.status === 'break_ended' && msg.success) {
            this.updateBadge('FREE');
            this.syncBreakUI('FREE');
            this.stopBreakCountdown();
        } else if (msg.status === 'break_rejected') {
            App.showToast(msg.message || 'Cannot start break now', 'error');
        }
    },
};
