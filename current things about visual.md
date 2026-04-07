# Current Things About Visual

This document captures the current implemented state of the Privex project, with focus on the Visual Firewall pipeline and its integrations.

## 1. Project Snapshot

Privex is currently organized as three main runtime modules:

1. `privex-core` (Python/FastAPI + LangGraph + Vision pipeline)
2. `privex-mcp` (Node.js Express + WebSocket bridge + screen capture agent)
3. `privex-ui` (React + Vite dashboard)

At this stage, the system already supports:

1. Screen frame capture every 2 seconds from Windows desktop
2. YOLO + OCR-based sensitive context detection
3. Human approval flow for high-risk visual alerts
4. Real-time alert broadcast to UI via WebSocket
5. Deterministic LLM routing + risk scoring for chat and approval logic
6. Audit logging into PostgreSQL-compatible table (`audit_log`)

## 2. Folder and Component Responsibilities

## Root Level

1. `docker-compose.yaml`: service orchestration for Neo4j, MCP, and Core CPU/GPU profiles
2. `README.md`: minimal project structure overview
3. `PRD.md`: product intent and architecture direction (some parts are aspirational, not fully implemented yet)
4. `.env.example`: cloud API key placeholders

## privex-core (Python)

1. `main.py`: FastAPI app startup, DB init, frame worker lifecycle, chat and alert resolution APIs, system tray boot path
2. `api/routes/vision.py`: frame ingest endpoint and human-decision logging endpoint
3. `services/frame_worker.py`: core Visual Firewall logic loop
4. `vision/engine.py`: YOLO model load, OCR utilities, trigger checks, redaction sanitization
5. `vision/tracker.py`: bounding box track state machine (TENTATIVE/ACTIVE/LOST/DELETED)
6. `core/graph.py`: LangGraph deterministic flow (router -> sub-agent -> risk engine)
7. `core/database.py`: async SQLAlchemy audit table management and event logging
8. `core/schemas.py`: Pydantic request schema contracts
9. `core/state.py`: typed shared state for graph execution
10. `os_integration/overlay.py`: Windows click-through redaction overlay renderer (Tkinter)
11. `os_integration/meeting_hook.py`: Windows registry-based webcam/mic activity gating
12. `os_integration/tray.py`: system tray icon and quit mechanism
13. `scripts/export_tensorrt.py`: optional TensorRT engine export utility
14. `scripts/test_engine.py`: model/engine latency sanity test

## privex-mcp (Node.js)

1. `server.js`: Express gateway and WebSocket alert fan-out
2. `src/screen_agent.js`: screenshot capture + resize + payload send to core API
3. `package.json`: Node dependencies for capture, active app detection, web server, WS transport
4. `Dockerfile`: container recipe for MCP service

## privex-ui (React)

1. `src/App.jsx`: WebSocket alert intake, active alert list, resolve-alert POST calls
2. `src/components/AlertCard.jsx`: threat card UI and approve/block controls
3. `src/components/LedgerTable.jsx`: audit log table fetched via MCP `/api/logs`
4. `src/components/ChatWidget.jsx`: chat interface to deterministic LangGraph result via MCP `/api/chat`
5. `src/components/SidebarNav.jsx`: navigation shell
6. `src/index.css`: global styles + Tailwind import
7. `vite.config.js`: Vite + Tailwind + React plugins

## 3. Current Technology Stack (Implemented)

## Core Backend

1. Python 3.11 (Docker base)
2. FastAPI + Uvicorn
3. Pydantic v2
4. SQLAlchemy async engine
5. HTTPX async client

## Agent/Reasoning

1. LangGraph state graph
2. LangChain community integrations
3. Ollama (`llama3:8b`) for local routing
4. Groq fallback (`llama3-8b-8192`) when `USE_CLOUD_LLM=true`
5. Ollama embeddings (`nomic-embed-text`)
6. PGVector integration (optional if available)

## Vision and OCR

1. Ultralytics YOLOv8 (`yolov8n.pt`)
2. OpenCV
3. PyTorch CUDA path
4. Tesseract via `pytesseract`
5. Optional TensorRT export/test scripts

## Node/MCP Layer

1. Node.js (ESM)
2. Express + CORS
3. WebSocket (`ws`)
4. `screenshot-desktop`
5. `sharp` for resize/compression
6. `active-win` for active window metadata

## UI

1. React 19
2. Vite 8
3. TailwindCSS 4
4. Lucide icons

## Data and Infra

1. PostgreSQL-compatible URL for `audit_log` table
2. Neo4j in Docker compose (declared; graph use is not fully wired in current runtime code)
3. Docker Compose with CPU/GPU profiles for core service

## 4. Algorithms and Detection Logic in Use

## 4.1 Deterministic Agent Graph

Current graph flow:

1. `llm_router_node`
2. Conditional route to `memory_agent` or `phishing_agent`
3. `risk_engine_node`
4. End

Determinism details:

1. LLM only chooses agent label
2. Risk is hardcoded by action (`search_local_memory` => Low, `send_external_email` => High)
3. Human approval requirement is code-enforced from risk result

## 4.2 Visual Firewall Detection Chain

For each accepted frame:

1. Decode base64 image
2. Skip processing if meeting is inactive
3. Skip self-monitoring apps by window-title ignore list (`privex-ui`, `localhost:5173`, `security console`, `gemini`, `chatgpt`, `claude`)
4. Run YOLO inference on frame
5. For each detected box:
6. Ignore near-fullscreen boxes (background suppression)
7. Crop box area (+5px padding)
8. OCR on crop
9. Sanitize OCR text with regex redaction
10. Trigger secret detection via keyword match (`password`, `api`, `secret`, `confidential`, `private`, `.env`, `key`)
11. Build `secret_boxes` only for triggered crops
12. If no secret boxes: tracker coasts and overlay clears/updates
13. If secret boxes exist: log event, ask memory agent for suppression decision, then alert and draw overlay

## 4.3 Tracking and Temporal Smoothing

`TrackManager` behavior:

1. Track states: TENTATIVE, ACTIVE, LOST, DELETED
2. Matching uses center-point Euclidean distance (`MATCH_DIST=400`)
3. `MIN_HITS=1` means immediate activation
4. `MAX_AGE=8` provides short persistence during OCR/inference jitter

This prevents overlay flicker and gives stable redaction boxes.

## 4.4 OCR Redaction Regex

Sanitization currently redacts:

1. AWS-style access keys (`AKIA...`)
2. Generic secret/token patterns (`secret key`, `access token`, etc.)
3. Password key-value formats (`password: ...`, `pass=...`)

Output text is normalized to reduce noisy newlines.

## 5. Inter-Service Connectivity (How Things Are Connected)

## 5.1 Frame Path

1. `privex-mcp/src/screen_agent.js` captures screenshot
2. Resizes to width 1280 and JPEG quality 70
3. Sends POST to `AI_CORE_URL` (expected `/api/analyze-frame`)
4. `privex-core` enqueues frame in queue (`maxsize=1` real-time drop-oldest)
5. Worker processes frame and potentially emits alert

## 5.2 Alert Path

1. `privex-core` posts alert to MCP `ALERT_ENDPOINT` (`/api/alert`)
2. `privex-mcp/server.js` broadcasts alert to all WebSocket clients
3. `privex-ui` receives alert via WebSocket and renders `AlertCard`

## 5.3 Human Decision Path

1. User clicks Approve/Block in UI
2. `privex-ui` sends POST to core `/api/resolve-alert`
3. Core can store OCR text into vector memory when approved
4. Core returns success and UI removes card from active queue

## 5.4 Chat Path

1. `ChatWidget` sends query to MCP `/api/chat`
2. MCP proxies to core `/api/chat`
3. Core invokes LangGraph and returns deterministic state fields

## 5.5 Ledger Path

1. UI fetches MCP `/api/logs`
2. MCP proxies to core `/api/logs`
3. Core reads recent `audit_log` rows from DB

## 6. Current APIs and Contracts

## Core APIs

1. `POST /api/analyze-frame` (202): queue incoming frame payload
2. `POST /api/resolve-alert` (200): record decision; optionally teach memory vector store
3. `POST /api/chat` (200): deterministic LangGraph result
4. `GET /api/logs?limit=50` (200): recent audit events

## MCP APIs

1. `POST /api/alert`: receives core alerts and broadcasts via WebSocket
2. `POST /api/chat`: proxy to core
3. `GET /api/logs`: proxy to core

## Frame Payload Schema

1. `base64_image: str`
2. `timestamp: float`
3. `source: str`
4. `active_app: object | null`

## 7. Current Workflow (Operational)

## Startup Workflow

1. Start DB/infra (Neo4j via compose, PostgreSQL separately if used by `DATABASE_URL`)
2. Start `privex-core` (FastAPI + frame worker + tray on Windows)
3. Start `privex-mcp` server (HTTP + WebSocket)
4. Start `screen_agent.js` loop for frame capture
5. Start `privex-ui` Vite app

## Runtime Workflow

1. Frames stream every ~2s
2. Worker only processes when meeting activity is detected
3. Secrets detected => audited event + overlay + high-risk alert
4. UI operator approves/blocks
5. Approved known-safe context can reduce future alert noise via vector recall
6. All key events are queryable in ledger table

## 8. Environment Variables in Use

Common variables currently referenced in code:

1. `AI_CORE_URL` (MCP screen agent -> core analyze endpoint)
2. `CORE_API_URL` (MCP proxy -> core base URL)
3. `ALERT_ENDPOINT` (core -> MCP alert endpoint)
4. `VITE_WS_URL` (UI websocket URL)
5. `VITE_MCP_API_URL` (UI chat proxy URL)
6. `VITE_LOGS_API_URL` (UI logs API URL)
7. `VITE_CORE_API_URL` (UI resolve alert URL)
8. `DATABASE_URL` / `PGVECTOR_CONNECTION`
9. `PGVECTOR_COLLECTION`
10. `MEMORY_MATCH_THRESHOLD`
11. `USE_CLOUD_LLM`
12. `EMBEDDING_MODEL`
13. `TESSERACT_CMD`
14. `PRIVEX_HOST`, `PRIVEX_PORT`

## 9. What Is Already Strong

1. End-to-end working visual pipeline with near real-time processing behavior
2. Deterministic risk gating instead of LLM-only decisions
3. Audit-oriented event logging structure
4. Human-in-the-loop UI action controls
5. Overlay redaction on Windows with tracking stability
6. Modular split between capture (MCP), intelligence/core, and UI

## 10. Current Gaps / Notes

1. `privex-mcp/Dockerfile` runs `npm start` but `package.json` currently has no `start` script.
2. `PRD.md` mentions features (full GraphRAG with Neo4j + pgvector + ontology pipeline, blockchain proofs, etc.) that are broader than currently wired runtime behavior.
3. Core DB fallback in code points to PostgreSQL, while compose currently includes Neo4j only (Postgres service is not declared in compose file).
4. There are two `/api/resolve-alert` handlers in core (`main.py` and `api/routes/vision.py`), and route behavior should stay intentionally aligned.

## 11. Quick End-to-End Summary

Privex currently works as a local-first Visual Firewall loop:

1. Screen is sampled in MCP
2. Core runs YOLO + OCR + regex sanitation + trigger checks
3. Risky visual contexts become audited alerts
4. Alerts stream to UI in real time
5. Human actions are enforced and recorded
6. Approved context can train future suppression behavior through vector memory

This is the implemented baseline state of the project right now.