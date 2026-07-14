const Employee = {
    timerInterval: null,
    activeTaskTimer: null,
    taskExpiryTime: 0,
    taskStartTime: 0,
    
    async init(data) {
        this.data = data;
        document.getElementById('emp-name').textContent = data.name;
        this.updateBadge(data.status);
        
        await this.loadZones();
        
        // Setup WS listeners
        ws.on('task_offer', (msg) => this.handleTaskOffer(msg));
        ws.on('task_reassigned', () => this.handleTaskReassigned());
        ws.on('status_update', (msg) => this.handleStatusUpdate(msg));
        
        // Setup UI bindings
        document.getElementById('zone-select').addEventListener('change', (e) => this.checkin(e.target.value));
        document.getElementById('ack-btn').addEventListener('click', () => this.ackTask());
        document.getElementById('complete-btn').addEventListener('click', () => this.completeTask());
        
        // Check if already assigned
        this.checkExistingTask();
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
        badge.textContent = status;
        badge.className = `badge ${status}`;
        this.data.status = status;
    },
    
    async checkExistingTask() {
        // Fetch active tasks for this employee
        const tasks = await api.get('/tasks/active/');
        if (tasks && tasks.length) {
            const myTask = tasks.find(t => t.assigned_employee === this.data.id);
            if (myTask) {
                this.currentTaskId = myTask.id;
                if (myTask.status === 'ASSIGNED') {
                    // Recreate offer card
                    this.showOfferCard(myTask.zone_name, 45); // Approximate
                } else if (myTask.status === 'ACKNOWLEDGED' || myTask.status === 'IN_PROGRESS') {
                    this.showActiveTask(myTask.zone_name, new Date(myTask.acknowledged_at));
                }
            }
        }
    },
    
    checkin(zoneId) {
        if (!zoneId) return;
        ws.send('checkin', {zone_id: zoneId});
    },
    
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
                this.hideOfferCard(); // Assume timeout, server will reassign
            }
        }, 1000);
    },
    
    hideOfferCard() {
        document.getElementById('task-offer-card').classList.add('hidden');
        if (this.timerInterval) clearInterval(this.timerInterval);
    },
    
    ackTask() {
        if (!this.currentTaskId) return;
        // Offline handling: if WS is down, send returns false and queues it
        const sent = ws.send('ack', {task_id: this.currentTaskId});
        if (!sent) {
            // Optimistically show active task if queued
            this.hideOfferCard();
            this.showActiveTask(document.getElementById('offer-zone-name').textContent, new Date());
            document.getElementById('active-task-panel').classList.add('offline-queued');
        }
    },
    
    completeTask() {
        if (!this.currentTaskId) return;
        const sent = ws.send('complete', {task_id: this.currentTaskId});
        
        this.hideActiveTask();
        this.updateBadge('FREE');
        
        if (!sent) {
            // Wait for queue drain, but locally we look FREE
        }
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
        
        this.updateBadge('BUSY');
    },
    
    hideActiveTask() {
        document.getElementById('active-task-panel').classList.add('hidden');
        if (this.activeTaskTimer) clearInterval(this.activeTaskTimer);
        this.currentTaskId = null;
    },
    
    handleTaskReassigned() {
        this.hideOfferCard();
        this.updateBadge('FREE');
        alert("Task was reassigned because time expired.");
    },
    
    handleStatusUpdate(msg) {
        if (msg.status === 'ack_result' && msg.success) {
            document.getElementById('active-task-panel').classList.remove('offline-queued');
            // Ensure UI is showing active
            if (document.getElementById('active-task-panel').classList.contains('hidden')) {
                this.showActiveTask(document.getElementById('offer-zone-name').textContent, new Date());
            }
        }
    }
};
