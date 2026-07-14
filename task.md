# Smart Employee Reallocation System — Task Tracker

## Phase 1: Project Scaffolding
- [ ] Create directory structure
- [ ] Create requirements.txt
- [ ] Create .env.example
- [ ] Create .gitignore

## Phase 2: Backend (Django + DRF + Channels)
- [ ] Initialize Django project (`backend/`)
- [ ] Create `core` app
- [ ] Data models (Zone, Employee, Task, TaskEvent)
- [ ] DRF serializers
- [ ] DRF views + URLs (REST API)
- [ ] Assignment engine (scoring + assignment)
- [ ] Task state machine (transitions + timeout checker)
- [ ] WebSocket consumer + routing
- [ ] Token auth middleware
- [ ] Redis subscriber (zone_alerts listener)
- [ ] ASGI configuration
- [ ] Settings (Channels, Redis, etc.)
- [ ] Seed management command
- [ ] Admin registration

## Phase 3: CV Worker
- [ ] config.py (all tunable values)
- [ ] capture.py (RTSP / video file capture + ring buffer)
- [ ] detector.py (ONNX inference + runtime NMS + person filter)
- [ ] zone_tracker.py (adaptive threshold + hysteresis)
- [ ] redis_publisher.py (metrics hash + pub/sub)
- [ ] snapshot.py (alert snapshot + 48h cleanup)
- [ ] main.py (entry point loop)

## Phase 4: Frontend PWA
- [ ] index.html (app shell)
- [ ] style.css (minimal dark theme)
- [ ] app.js (main logic, routing, state)
- [ ] ws.js (WebSocket + exponential backoff reconnect)
- [ ] api.js (REST client + offline queue)
- [ ] employee.js (employee view)
- [ ] manager.js (manager dashboard view)
- [ ] sw.js (service worker: cache + queue)
- [ ] manifest.json
- [ ] PWA icons

## Phase 5: Scripts & Utilities
- [ ] download_model.py
- [ ] simulate_crowd.py
- [ ] run_all.py

## Phase 6: Documentation
- [ ] README.md

## Phase 7: Verification
- [ ] Start services and verify end-to-end flow in browser
