Product Requirements Document (PRD) v4.0 (Native Edge Architecture)
Project: Privex – Privacy-First Personal AI Guardian

1. Product Overview
1.1 Vision & Core Philosophy
Privex is a local-first, privacy-preserving agentic AI system. It protects and organizes a user’s digital life via continuous observation of documents, emails, screen activity, browsing behavior, and chat logs. The core philosophy relies on:


Zero-Trust Modularity: No individual module implicitly trusts the input of another.


Code Decides Flow, LLM Assists: The orchestrator is pure deterministic code ; the LLM is only utilized for narrow reasoning and routing tasks.
Algorithmic Privilege Separation: The LLM can only suggest actions ; deterministic Python runtime logic physically enforces the Human-in-the-Loop approval gate.
ecision and access is cryptographically recorded to create an auditable proof of behavior.

2. Core System Architecture & IPC
2.1 The Deterministic State Graph (LangGraph)
The system abandons open-ended LLM planning in favor of a strictly defined state machine.


The LLM Router: The user query hits the Orchestrator, which asks the LLM a single question: "Which specific agent should handle this?" 


Isolated Sub-Agents: The request is routed to a specialized, deterministic workflow (e.g., Memory Agent, Phishing Agent, Screen Agent).


The Deterministic Risk Engine: Once an agent proposes an action, it passes through a hardcoded Python Risk Dictionary (NOT an LLM decision) to determine if human approval is required.

2.2 Inter-Process Communication (IPC)

Native Windows Loopback: The architecture runs natively on the Windows Host, bypassing virtualization layers. Communication between the Node.js MCP layer and the Python AI backend occurs via standard JSON over HTTP (127.0.0.1). Real-time alerts utilize WebSockets.


Trigger-Based Sampling: To prevent JSON serialization bottlenecks, the Screen MCP captures one frame every 2 seconds, downscales it, and sends it as a base64 encoded payload.


The .env Provider Fallback: For decoupled development, the system utilizes a .env variable (e.g., LLM_PROVIDER=groq or LLM_PROVIDER=ollama) to temporarily route reasoning tasks to a Cloud API before final integration with the local Ollama instance.

3. Core Functional Modules
3.1 Edge-Optimized Screen Privacy Guard (Visual Firewall)
Detects sensitive information on the user’s screen.

Hardware Inference: Inference runs natively on Windows via standard PyTorch (yolov8n.pt) leveraging CUDA for local GPU acceleration. Sampled frames are pushed into an asynchronous queue, bypassing the LLM entirely until a high-risk semantic flag is detected.

OCR Integration: When UI elements are detected, OCR extracts the embedded text to provide semantic context to the Risk Engine.

3.2 Adaptive GraphRAG (Memory Agent)
Stores a searchable memory of past activities from documents, screenshots, and chats.

Polyglot Storage: Utilizes Neo4j for complex entity relationship mapping and PostgreSQL (pgvector) for flat semantic similarity and fast retrieval.


Pipeline Flow: Ontology Grounding -> Vector Indexing -> K-Nearest Neighbor (KNN) clustering -> Weakly Connected Components (WCC) -> LLM Consensus & Refactoring.


Result: Background deduplication prevents hallucinated relationships and physically collapses duplicate nodes in Neo4j while preserving topological edges.

4. Human-in-the-Loop Governance
The LLM never directly executes code. Proposed actions are intercepted by the deterministic Risk Engine.

Search local memory / Summarize -> Low Risk -> No Approval 

Create calendar reminder -> Medium Risk -> Optional Approval 

Send an external email -> High Risk -> Mandatory Approval 

Modify local files / Delete data -> Critical Risk -> Mandatory Approval 

7. Technical Stack


Core Logic: Python (FastAPI, LangGraph) & Node.js (Express).


AI Models: Local models via Ollama (Llama-3, Phi-3) + .env Cloud API Fallback.


Computer Vision: OpenCV, YOLOv8 PyTorch (.pt), EasyOCR/Tesseract.


Storage: * Neo4j: Graph Database (Adaptive GraphRAG / Entity Relationships).


PostgreSQL + pgvector: Relational Audit Ledger & Vector Store.


Blockchain: Web3.py / ethers.js.