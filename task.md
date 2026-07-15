# Smart Employee Reallocation System — Task Tracker

## Phase 1: Project Scaffolding
- [x] Create directory structure
- [x] Create requirements.txt
- [x] Create .env.example
- [x] Create .gitignore

## Phase 2: Backend (Django + DRF + Channels)
- [x] Initialize Django project (`backend/`)
- [x] Create `core` app
- [x] Data models (Zone, Employee, Task, TaskEvent)
  - [x] Added `username` + `password_hash` fields for login/register (migration 0002)
- [x] DRF serializers
- [x] DRF views + URLs (REST API)
  - [x] `POST /api/auth/token/` — login with username + password
  - [x] `POST /api/auth/register/` — self-register new employee
- [x] Assignment engine (scoring + assignment)
- [x] Task state machine (transitions + timeout checker)
- [x] WebSocket consumer + routing
- [x] Token auth middleware
- [x] Redis subscriber (zone_alerts listener)
- [x] ASGI configuration
- [x] Settings (Channels, Redis, etc.)
- [x] Seed management command (demo: alice/bob/.../frank, password: demo1234)
- [x] Admin registration

## Phase 3: CV Worker
- [x] config.py
- [x] capture.py
- [x] detector.py
- [x] zone_tracker.py
- [x] redis_publisher.py
- [x] snapshot.py
- [x] main.py

## Phase 4: Frontend PWA
- [x] index.html (premium dark theme, animated orb background)
- [x] style.css (glassmorphism, Inter font, micro-animations)
- [x] app.js (login + register + tab switching + toasts)
- [x] ws.js
- [x] api.js
- [x] employee.js
- [x] manager.js
- [x] sw.js
- [x] manifest.json

## Phase 5: Scripts & Utilities
- [x] download_model.py
- [x] simulate_crowd.py
- [x] run_all.py

## Phase 6: Documentation
- [x] README.md

## Phase 7: Verification
- [x] Start services and verify end-to-end flow in browser
- [x] Test login (alice / demo1234)
- [x] Test register (new account creation)
- [x] Confirm task offer → ACK → complete loop
- [x] Validate timeout checker runs successfully
