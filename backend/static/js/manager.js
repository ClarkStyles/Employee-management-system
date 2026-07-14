const Manager = {
    pollingInterval: null,
    
    async init() {
        this.refreshData();
        
        // Connect WS just to listen for zone_updates
        // We can use a generic dummy token if real auth isn't needed for dashboard in demo
        // Or we rely on polling. The spec asks for a simple view.
        // Let's rely on REST polling for simplicity of demo, 
        // but we'll also try to hook WS if a token exists.
        
        this.pollingInterval = setInterval(() => this.refreshData(), 3000);
    },
    
    async refreshData() {
        const [zones, history] = await Promise.all([
            api.get('/zones/status/'),
            api.get('/tasks/history/')
        ]);
        
        if (zones) this.renderZones(zones);
        if (history) this.renderStats(history);
        
        const activeTasks = await api.get('/tasks/active/');
        if (activeTasks) this.renderActiveTasks(activeTasks);
    },
    
    renderZones(zones) {
        const grid = document.getElementById('zones-grid');
        grid.innerHTML = '';
        
        zones.forEach(z => {
            const densityPct = Math.min(100, Math.round((z.current_threshold.density) * 100));
            // Actual density from real metrics isn't in DB (it's in Redis), 
            // but the state is. For demo, we highlight state.
            
            const card = document.createElement('div');
            card.className = `zone-card ${z.current_state}`;
            card.innerHTML = `
                <div class="zone-header">
                    <h4>${z.name}</h4>
                    <span class="zone-state">${z.current_state}</span>
                </div>
                <p>Checked in: ${z.checked_in_employees.length}</p>
                <p>Active Tasks: ${z.active_task_count}</p>
            `;
            grid.appendChild(card);
        });
    },
    
    renderStats(history) {
        if (!history || !history.metrics) return;
        const m = history.metrics;
        
        document.getElementById('mgr-tasks-today').textContent = m.tasks_today || 0;
        
        if (m.avg_response_time) {
            document.getElementById('mgr-avg-response').textContent = Math.round(m.avg_response_time) + 's';
        } else {
            document.getElementById('mgr-avg-response').textContent = '-';
        }
    },
    
    renderActiveTasks(tasks) {
        const list = document.getElementById('active-tasks-list');
        list.innerHTML = '';
        
        if (tasks.length === 0) {
            list.innerHTML = '<p>No active tasks.</p>';
            return;
        }
        
        tasks.forEach(t => {
            const el = document.createElement('div');
            el.className = 'task-item';
            
            let empName = t.assigned_employee_name || 'Unassigned';
            let attention = t.needs_manager_attention ? '<span style="color:red">⚠️ Escalated</span>' : '';
            
            el.innerHTML = `
                <div><strong>Zone:</strong> ${t.zone_name} ${attention}</div>
                <div><strong>Assigned:</strong> ${empName}</div>
                <div><strong>Status:</strong> ${t.status} (Reassignments: ${t.reassignment_count})</div>
            `;
            list.appendChild(el);
        });
    },
    
    destroy() {
        if (this.pollingInterval) {
            clearInterval(this.pollingInterval);
        }
    }
};
