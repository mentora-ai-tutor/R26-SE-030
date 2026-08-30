# RAG Architecture - AME Agent

This document describes the Retrieval-Augmented Generation (RAG) layer added to the
Assessment and Mastery Evaluation (AME) Agent. The RAG layer grounds the LLM-powered
question generation and feedback with content from a curated knowledge base, without
changing the existing n8n workflow or any other service.

---

## Overview

```
┌─────────────────────────────────────────────────────────────────────┐
│                         Knowledge Source                             │
│            (curriculum, lecture notes, textbooks, question bank)     │
└──────────────────────────────┬──────────────────────────────────────┘
                               │ POST /api/ame/rag/ingest
                               ▼
┌─────────────────────────────────────────────────────────────────────┐
│                    INGESTION PIPELINE (ragService)                  │
│                                                                     │
│  Split into chunks (RAG_CHUNK_SIZE / RAG_CHUNK_OVERLAP)             │
│              │                                                      │
│              ▼                                                      │
│  Embed with Ollama (OLLAMA_EMBEDDING_MODEL)                         │
│              │                                                      │
│              ▼                                                      │
│  Store in MongoDB                                                  │
│   ├─ ame_knowledge_documents  (document metadata)                  │
│   └─ ame_knowledge_chunks     (text + embedding vector)            │
└──────────────────────────────┬──────────────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────────────┐
│                         RETRIEVAL PIPELINE                          │
│                                                                     │
│  start-session: query = each knowledge-gap topic                    │
│  submit-answer: query = current question topic + text               │
│              │                                                      │
│              ▼                                                      │
│  Embed the query (same model)                                       │
│              │                                                      │
│              ▼                                                      │
│  Cosine similarity over ame_knowledge_chunks  → top-K chunks        │
│  (keyword search fallback if embedding unavailable)                 │
└──────────────────────────────┬──────────────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────────────┐
│                         GENERATION (n8n + Ollama)                   │
│                                                                     │
│  Payload → n8n webhook carries `rag_context`                        │
│  (retrieved chunks). n8n workflow may inject them into the          │
│   question-generation / feedback prompts.                           │
│  Adding rag_context is NON-BREAKING: the workflow only validates    │
│   existing required fields and ignores unknown ones.                │
└─────────────────────────────────────────────────────────────────────┘
```

---

## Why this design

- **No new infrastructure.** Vectors are stored in MongoDB and similarity is computed
  in-process (cosine). Works on local MongoDB or MongoDB Atlas without creating a
  vector-search index.
- **Reuses the existing stack.** Embeddings come from the same Ollama instance already
  used by the n8n workflows (`OLLAMA_BASE_URL`), default model `nomic-embed-text:cpu`.
- **Non-breaking.** The n8n workflow and all existing endpoints behave exactly as before.
  RAG is additive: if the knowledge base is empty, embedding fails, or `RAG_ENABLED=false`,
  requests simply skip context enrichment.

---

## Collections

### `ame_knowledge_documents`

One document per ingested knowledge source.

| Field | Type | Description |
|---|---|---|
| `document_id` | String | Unique document identifier (defaults to `DOC_<timestamp>`) |
| `title` | String/null | Document title |
| `topic` | String/null | Topic tag used for filtering |
| `source` | String/null | Source/origin of the content |
| `chunk_count` | Number | Number of chunks produced |
| `total_chars` | Number | Total character count of content |
| `metadata` | Object | Arbitrary caller-provided metadata |
| `created_at` | Date | First ingestion time |
| `updated_at` | Date | Last ingestion time |

### `ame_knowledge_chunks`

One document per embedded chunk.

| Field | Type | Description |
|---|---|---|
| `chunk_id` | String | Unique chunk id (`<document_id>_CHUNK_<n>`) |
| `document_id` | String | Parent document |
| `title` | String/null | Inherited document title |
| `topic` | String/null | Inherited topic (used for filtering) |
| `source` | String/null | Inherited source |
| `chunk_index` | Number | Order within the document |
| `content` | String | The chunk text |
| `metadata` | Object | Inherited document metadata |
| `embedding` | Array<Number> | Embedding vector |
| `ingested_at` | Date | Ingestion timestamp |

> Ingesting the same `document_id` again is **idempotent**: old chunks are deleted and
> replaced, and the document metadata is refreshed.

---

## API

All endpoints are under `/api/ame/rag` and require a **Bearer JWT** (`auth` middleware).

### `POST /api/ame/rag/ingest`

Ingest (or re-ingest) a knowledge document.

```json
{
  "document_id": "KB_RECURSION_01",
  "title": "Recursion Fundamentals",
  "topic": "Recursion",
  "source": "curriculum/unit-04",
  "content": "Recursion is a method that calls itself...",
  "metadata": { "course": "CS101", "chapter": 4 },
  "chunk_size": 800,
  "chunk_overlap": 120
}
```

**Response `200`:**
```json
{
  "success": true,
  "message": "Document ingested into the knowledge base",
  "data": { "document_id": "KB_RECURSION_01", "chunk_count": 12 }
}
```

### `POST /api/ame/rag/retrieve`

Semantic search over the knowledge base.

```json
{
  "query": "Why does recursion need a base case?",
  "topic": "Recursion",
  "top_k": 5,
  "threshold": 0.25
}
```

**Response `200`:**
```json
{
  "success": true,
  "data": {
    "query": "Why does recursion need a base case?",
    "top_k": 3,
    "retrieval": "embedding",
    "chunks": [
      {
        "score": 0.71,
        "chunk_id": "KB_RECURSION_01_CHUNK_2",
        "document_id": "KB_RECURSION_01",
        "title": "Recursion Fundamentals",
        "topic": "Recursion",
        "source": "curriculum/unit-04",
        "content": "The base case terminates recursive calls...",
        "metadata": { "course": "CS101", "chapter": 4 }
      }
    ]
  }
}
```

`retrieval` is `"embedding"` when cosine similarity was used, `"keyword"` when the
embedding step failed and the keyword fallback took over.

### `GET /api/ame/rag/documents`

List knowledge base documents. Supports `?page=` and `?limit=`.

### `GET /api/ame/rag/documents/:documentId`

Fetch a document together with all of its chunks (embeddings excluded).

### `DELETE /api/ame/rag/documents/:documentId`

Delete a document and its chunks.

### `GET /api/ame/rag/stats`

```json
{
  "success": true,
  "data": {
    "enabled": true,
    "documents": 3,
    "chunks": 47,
    "topics": ["Recursion", "Arrays", "OOP"],
    "embedding_dimensions": 768,
    "average_chunks_per_document": 15.67,
    "documents_ids": ["KB_RECURSION_01", "..."]
  }
}
```

---

## Automatic context enrichment

The existing flows are automatically enriched (only when `RAG_ENABLED=true`):

- **`POST /api/ame/start-session`** — for every topic in `mastery_profile.knowledge_gaps`,
  top-3 chunks are retrieved and attached to the n8n payload as `rag_context`:
  ```json
  {
    "student_id": "STU-123",
    "mastery_profile": { "...": "..." },
    "rag_context": {
      "query": "Recursion",
      "topics": ["Recursion"],
      "chunks": [ { "score": 0.71, "content": "...", "...": "..." } ]
    }
  }
  ```
- **`POST /api/ame/submit-answer`** — the current question's topic + text are used to
  retrieve context and attach it as `rag_context` on the payload.

Because the n8n workflow only validates the fields it already reads (`student_id`,
`mastery_profile.knowledge_gaps`, `session_id`, `question_id`, `answer`), the extra
`rag_context` field is ignored — nothing breaks. If you later want the LLM to consume the
context, reference `body.rag_context` inside the n8n prompt-building nodes.

> Enrichment is best-effort: retrieval errors, an empty knowledge base, or a disabled
> RAG flag never fail the underlying request.

---

## Configuration

| Variable | Default | Description |
|---|---|---|
| `OLLAMA_BASE_URL` | `http://localhost:11434` | Ollama endpoint used for embeddings |
| `OLLAMA_EMBEDDING_MODEL` | `nomic-embed-text:cpu` | Embedding model (must be pulled in Ollama) |
| `OLLAMA_EMBEDDING_TIMEOUT` | `30000` | Embedding request timeout (ms) |
| `RAG_ENABLED` | `true` | Master switch for RAG enrichment |
| `RAG_TOP_K` | `5` | Default number of chunks returned by retrieval |
| `RAG_MIN_SCORE` | `0.25` | Minimum cosine similarity threshold |
| `RAG_CHUNK_SIZE` | `800` | Target chunk size (characters) |
| `RAG_CHUNK_OVERLAP` | `120` | Overlap between consecutive chunks |

---

## Getting started

1. Pull the embedding model: `ollama pull nomic-embed-text` (on machines where the
   Ollama CUDA build cannot load the GPU driver, create a CPU variant with
   `ollama create nomic-embed-text:cpu -f <(echo "FROM nomic-embed-text`nPARAMETER num_gpu 0")`
   and set `OLLAMA_EMBEDDING_MODEL=nomic-embed-text:cpu`).
2. Set `RAG_ENABLED=true` and `OLLAMA_BASE_URL` in `.env`.
3. Ingest your curriculum/knowledge documents via `POST /api/ame/rag/ingest`.
4. Verify with `POST /api/ame/rag/retrieve` and `GET /api/ame/rag/stats`.
5. Start `start-session` / `submit-answer` as usual — `rag_context` is attached
   automatically when the knowledge base returns relevant chunks.
