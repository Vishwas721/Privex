# Privex — Building a Privacy-First Personal AI Guardian

## Why I Built This

I wanted to explore what a personal AI system could look like if **privacy and control were treated as core engineering requirements**, rather than features added later.

The idea behind Privex is simple: an AI system that can observe and organize parts of a user's digital life — documents, screen activity, chats, and other local data — while keeping sensitive processing on the user's machine whenever possible.

The interesting part wasn't just getting an LLM to work. It was figuring out **how much control an LLM should actually have**.

That led to the core principle behind Privex:

> **Code decides flow. LLM assists.**

---

## The Main Design Problem

A typical agentic system gives an LLM a set of tools and lets it decide what to do next.

For Privex, I didn't want to completely trust that approach.

If an AI assistant can access personal data or perform actions on behalf of a user, giving the model unrestricted control creates a difficult question:

**What stops the model from making a bad decision?**

My solution was to separate **reasoning from execution**.

The LLM can interpret a request, route it to the appropriate agent, and suggest an action. But it cannot directly execute that action.

The actual execution path is controlled by deterministic code.

---

## Architecture

The system uses a deterministic state graph built with LangGraph.

At a high level:

```text
User Request
     ↓
Orchestrator
     ↓
LLM Router
     ↓
Specialized Agent
     ↓
Proposed Action
     ↓
Deterministic Risk Engine
     ↓
Human Approval (if required)
     ↓
Action
```

The LLM's job is intentionally narrow.

For example, a request might be routed to a Memory Agent, Screen Agent, or Phishing Agent. Once that specialized workflow proposes an action, the deterministic Risk Engine evaluates the action.

The LLM does **not** get to decide whether an action is safe.

---

## Deterministic Risk & Human-in-the-Loop

I created a hardcoded risk dictionary that separates actions by their potential impact.

For example:

| Action                     | Risk     | Approval     |
| -------------------------- | -------- | ------------ |
| Search local memory        | Low      | Not required |
| Summarize information      | Low      | Not required |
| Create a calendar reminder | Medium   | Optional     |
| Send an external email     | High     | Required     |
| Modify local files         | Critical | Required     |
| Delete data                | Critical | Required     |

This creates a physical separation between **what the AI suggests** and **what the system actually allows**.

The goal is that even if the LLM produces an unexpected output, it cannot bypass the deterministic approval layer.

---

## Local-First Architecture

Privacy was also a major architectural constraint.

Privex is designed to run natively on Windows rather than depending on a virtualized environment.

The Node.js MCP layer communicates with the Python AI backend through standard JSON over local HTTP using `127.0.0.1`, while WebSockets are used for real-time alerts.

For development, I also added an environment-based provider fallback. This allows reasoning tasks to temporarily use a cloud provider while the final system can be switched to a local Ollama model.

The goal is to keep the architecture modular without making development unnecessarily difficult.

---

## Screen Privacy Guard

One of the more interesting components is the visual firewall.

The system periodically samples the user's screen and processes frames locally.

Instead of sending every frame to an LLM, the pipeline uses traditional computer vision first:

```text
Screen
  ↓
Frame Sampling
  ↓
YOLOv8
  ↓
OCR
  ↓
Semantic Context
  ↓
Risk Engine
```

YOLOv8 handles visual detection while OCR extracts text from detected UI elements.

The important design decision here was to **avoid involving the LLM unless it is actually necessary**.

This keeps the pipeline faster and reduces the amount of sensitive information that needs to reach a language model.

---

## Adaptive GraphRAG Memory

Another major part of Privex is its memory system.

I wanted the system to be able to retrieve information based not only on semantic similarity, but also on relationships between entities.

To do this, Privex combines:

* **PostgreSQL + pgvector** for semantic/vector retrieval
* **Neo4j** for entity relationships and graph-based retrieval

The pipeline follows:

```text
Raw Information
      ↓
Ontology Grounding
      ↓
Vector Indexing
      ↓
KNN Retrieval
      ↓
Graph Processing
      ↓
LLM Consensus
      ↓
Memory
```

A challenge here is that continuously ingesting information can create duplicate or incorrect relationships.

To deal with this, the system uses background deduplication and graph cleanup. Perceptual hashing, temporal debouncing, and structured extraction help prevent duplicate information from creating unnecessary graph nodes or relationships.

---

## What I Found Most Interesting

The most interesting part of building Privex wasn't any individual model.

It was the **boundary between probabilistic AI and deterministic software**.

LLMs are very good at interpreting ambiguous information and making useful suggestions, but they aren't something I want controlling sensitive operations without constraints.

That led me to design the system around a simple separation:

**LLM → Reasoning**

**Code → Control**

**Human → Final authority**

That separation is probably the part of Privex I'm most interested in continuing to explore.

---

## What I'd Improve Next

The current architecture gives me a strong foundation, but there are still several areas I'd like to improve.

I'd like to make the memory system more efficient as the amount of stored information grows, improve the evaluation methodology for retrieval quality, and further reduce unnecessary model calls.

I'd also like to explore better ways of measuring whether the risk engine is correctly identifying actions that actually require human approval.

For me, Privex is less about building another chatbot and more about exploring what **safe, useful, local-first agentic software** can look like when the AI isn't given unrestricted control.
