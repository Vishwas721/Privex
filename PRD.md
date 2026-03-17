Product Requirements Document (PRD) v3.0 (Final Architecture)
Project: Privex – Privacy-First Personal AI Guardian
1. Product Overview
1.1 Vision & Core Philosophy
Privex is a local-first, privacy-preserving agentic AI system. It protects and organizes a user’s digital life via continuous observation of documents, emails, screen activity, browsing behavior, and chat logs. The core philosophy relies on:

Zero-Trust Modularity: No individual module implicitly trusts the input of another.

Code Decides Flow, LLM Assists: The orchestrator is pure deterministic code; the LLM is only utilized for narrow reasoning and routing tasks.

Algorithmic Privilege Separation: The LLM can only suggest actions; deterministic Python runtime logic physically enforces the Human-in-the-Loop approval gate.

Verifiable Transparency: Every decision and access is cryptographically recorded to create an auditable proof of behavior.

2. Core System Architecture & IPC
2.1 The Deterministic State Graph (LangGraph)
The system abandons open-ended LLM planning in favor of a strictly defined state machine.

The LLM Router: The user query hits the Orchestrator, which asks the LLM a single question: "Which specific agent should handle this?"

Isolated Sub-Agents: The request is routed to a specialized, deterministic workflow (e.g., Memory Agent, Phishing Agent, Screen Agent).

The Risk Engine: Once an agent proposes an action, it passes through a hardcoded Risk Dictionary (not an LLM decision) to determine if human approval is required.

2.2 Inter-Process Communication (IPC)
To prioritize development velocity while maintaining stability, the system utilizes standard web protocols coupled with strategic rate-limiting:

REST APIs & WebSockets: Communication between the Node.js MCP layer and the Python AI backend occurs via standard JSON over HTTP (FastAPI/Express). Real-time alerts utilize WebSockets.

Trigger-Based Sampling: To prevent JSON serialization bottlenecks, the Screen MCP does not stream 60fps video. It captures one frame every 2 seconds, downscales it to 640x640, and sends it as a base64 encoded payload.

The .env Cloud Fallback: For decoupled development across different hardware profiles, the UI and MCP layer utilize a .env variable to temporarily route heavy reasoning tasks to a free Cloud API (e.g., Groq) before final integration with the local Ollama instance.

3. Core Functional Modules
3.1 Edge-Optimized Screen Privacy Guard (Visual Firewall)
Detects sensitive information on the user’s screen, such as passwords, API keys, credit cards, and private emails.

Hardware Inference: The YOLOv8 model is compiled into an NVIDIA TensorRT engine (INT8/FP16). Sampled frames are pushed into an asynchronous queue, bypassing the LLM entirely until a high-risk semantic flag is detected.

3.2 Adaptive GraphRAG (Memory Agent)
Stores a searchable memory of past activities from documents, screenshots, and chats.

Pipeline Flow: Ontology Grounding -> Vector Indexing -> K-Nearest Neighbor (KNN) clustering -> Weakly Connected Components (WCC) -> LLM Consensus & Refactoring.

Result: Background deduplication prevents hallucinated relationships and physically collapses duplicate nodes while preserving topological edges.

3.3 Phishing Agent
Detects malicious websites and scam emails using deterministic steps: extracting URLs, looking up domain age, scanning headers, and applying heuristics to generate a risk score.

4. Advanced Security & Privacy Infrastructure
4.1 Semantic Privacy Anomaly Detection and Remediation (SPADR)
Extracting semantic data while dropping pixels does not guarantee privacy.

Aggressive NER Scrubbing: A localized model (e.g., Microsoft Presidio) scans all OCR output for PII, API keys, and credit cards before embedding generation.

Intent-Based Token Replacement: Detected sensitive strings are irrevocably replaced with semantic tokens (e.g., <REDACTED_API_KEY>).

4.2 Indirect Prompt Injection (IDPI) Defense
To prevent a malicious document from overriding the local orchestrator:

Data Segregation: RAG context is isolated using randomized data delimiters.

Prompt WAF: A highly optimized classifier evaluates retrieved chunks for jailbreak signatures before they enter the LLM's context window.

5. Human-in-the-Loop Governance
The LLM never directly executes code. Proposed actions are intercepted by the deterministic Risk Engine.

Proposed Action,Hardcoded Risk Level,Human Approval Required
Search local memory / Summarize,Low,No
Create calendar reminder,Medium,Optional
Send an external email,High,Mandatory
Modify local files / Delete data,Critical,Mandatory

6. Cryptographic Audit System
Ensures all AI decisions are traceable by cryptographically logging the timestamp, action type, context hash, and user approval status. No sensitive data is ever stored on-chain.

Merkle Tree Batching: The system hashes all accessed data chunks (using SHA256), constructs a deterministic Merkle tree locally, and logs only the single Root Hash to a fast L2 blockchain (e.g., Polygon, Arbitrum, or Base testnet).

7. Technical Stack
Core Logic: Python (FastAPI, LangGraph) & Node.js (Express).

AI Models: Local models via Ollama (Llama-3, Mistral, Qwen) + .env Cloud API Fallback.

Computer Vision: OpenCV, YOLOv8, Tesseract OCR.

Storage: Neo4j (Graph), Chroma/FAISS (Vectors), SQLite (State).

Blockchain: Web3.py / ethers.js.

Environments: Unified Docker Compose utilizing gpu-enabled and cpu-fallback profiles.