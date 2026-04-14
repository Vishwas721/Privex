# Privex Database Architecture

## 1. Vector Store (PostgreSQL + pgvector)
We use `langchain_postgres` to manage our vector embeddings. 
**CRITICAL AI INSTRUCTION:** Langchain uses the column name `cmetadata` (Custom Metadata), NEVER `metadata`.

**Table: `langchain_pg_collection`**
* `uuid` (UUID PRIMARY KEY)
* `name` (VARCHAR UNIQUE) - The namespace for the vectors (e.g., 'screen_memories').
* `cmetadata` (JSON)

**Table: `langchain_pg_embedding`**
* `id` (VARCHAR PRIMARY KEY)
* `collection_id` (UUID) - Foreign Key linked to `langchain_pg_collection.uuid`.
* `embedding` (VECTOR)
* `document` (VARCHAR) - The summarized memory or raw OCR text.
* `cmetadata` (JSONB) - Contains keys:
  * `active_app` (String)
  * `timestamp` (ISO-8601 String)
  * `type` (String, e.g., 'daily_summary')
  * `alert_id` (String, if approved from UI)

## 2. Audit Ledger (PostgreSQL Relational)
**Table: `audit_log`**
* `id` (TEXT PRIMARY KEY)
* `timestamp` (TEXT)
* `event_type` (TEXT)
* `details` (TEXT - JSON string)
* `hash` (TEXT - SHA256 canonical hash)