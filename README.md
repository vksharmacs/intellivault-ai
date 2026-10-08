<div align="center">

# IntelliVault AI

### Secure, Bilingual Retrieval-Augmented Generation for Your Documents

**English / Hindi · React · FastAPI · PostgreSQL + pgvector · Redis + Celery · Ollama · S3 · Prometheus + Grafana**

[![CI](https://img.shields.io/badge/CI-GitHub%20Actions-2088FF?logo=githubactions&logoColor=white)](#testing-and-devsecops)
[![Python](https://img.shields.io/badge/Python-3.12-3776AB?logo=python&logoColor=white)](#technology-stack)
[![FastAPI](https://img.shields.io/badge/FastAPI-API-009688?logo=fastapi&logoColor=white)](#technology-stack)
[![React](https://img.shields.io/badge/React-Frontend-61DAFB?logo=react&logoColor=black)](#technology-stack)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-pgvector-4169E1?logo=postgresql&logoColor=white)](#technology-stack)
[![Docker](https://img.shields.io/badge/Docker-Ready-2496ED?logo=docker&logoColor=white)](#run-the-production-stack-locally)

**Version 1.0.0 · October 2026**

</div>

---

## Overview

**IntelliVault AI** is a production-oriented, multi-user Retrieval-Augmented Generation (RAG) knowledge assistant. Authenticated users can upload PDF documents and ask questions in **English or Hindi**. The system retrieves relevant document passages, reranks them, generates a grounded answer, streams the response to the browser, and displays PDF/page-level evidence.

The project is designed to demonstrate not only RAG, but the engineering required around it: authentication, user isolation, asynchronous ingestion, vector retrieval, caching, object storage, observability, security controls, automated migrations, testing, CI security scanning, and cloud deployment.

### Highlights

- 🔐 JWT authentication with Argon2 password hashing
- 👥 User-scoped documents and retrieval
- 📄 Multi-page PDF ingestion and page-aware citations
- 🧠 SentenceTransformer embeddings and PostgreSQL/pgvector retrieval
- 🎯 Cross-Encoder reranking
- 💬 English/Hindi grounded answers
- ⚡ Ollama response streaming
- 📊 TTFT, retrieval, reranking, generation, and total latency metrics
- 🧰 Redis caching and Celery background ingestion
- ☁️ Private S3-compatible object storage
- 🛡️ PDF validation and ClamAV malware scanning
- 📈 Prometheus and Grafana observability
- 🔄 Alembic database migrations
- 🧪 Backend, storage, multi-page PDF, and security tests
- 🔎 CodeQL, Trivy, dependency audits, and Dependabot
- 🚂 Railway deployment configuration
- 💻 Docker-free development mode for lightweight local testing

---

## Architecture

```text
                               Internet
                                  │
                       ┌──────────┴──────────┐
                       ▼                     ▼
                React + Nginx             FastAPI
                   Frontend                  │
                                             │ JWT
              ┌──────────────────────────────┼──────────────────────────────┐
              │                              │                              │
              ▼                              ▼                              ▼
      S3-compatible storage                Redis                    PostgreSQL
         Private PDFs                 cache + broker                 + pgvector
              │                              │                              │
              │                              ▼                              │
              │                        Celery Worker                        │
              │                              │                              │
              └──────────────────────────────┼──────────────────────────────┘
                                             ▼
                                  Parse → Chunk → Embed
                                             │
                                             ▼
                                      pgvector Top-K
                                             │
                                             ▼
                                      Cross-Encoder
                                         reranking
                                             │
                                             ▼
                                           Ollama
                                             │
                                      streamed answer
                                             │
                                             ▼
                              PDF/page citations + metrics

                         Prometheus ─────→ Grafana
                         ClamAV ─────────→ upload scanning
```

---

## RAG Pipeline

```text
Question
   ↓
Answer cache lookup
   ↓
Query embedding
   ↓
pgvector cosine retrieval
   ↓
Cross-Encoder reranking
   ↓
Grounded context with source metadata
   ↓
Ollama generation
   ↓
Streaming response
   ↓
Document + page citations
```

Retrieval is scoped to the authenticated user, preventing normal document search from crossing user boundaries.

---

## Technology Stack

| Layer | Technology | Purpose |
|---|---|---|
| Frontend | React, Vite, Axios | Authentication, document management, chat, streaming UI |
| API | FastAPI | Auth, uploads, retrieval orchestration, streaming and metrics |
| Authentication | JWT, Argon2 | Identity, protected routes and password hashing |
| Database | PostgreSQL, SQLAlchemy | Users, documents, chunks and application state |
| Vector Search | pgvector, HNSW | Semantic similarity search |
| Embeddings | SentenceTransformers | 384-dimensional semantic vectors |
| Reranking | Cross-Encoder | Improve retrieved-context relevance |
| LLM | Ollama | Local/private grounded answer generation |
| Queue | Celery, Redis | Asynchronous PDF ingestion |
| Cache | Redis | Repeated query/answer caching |
| Object Storage | S3-compatible storage | Private durable PDF storage |
| Malware Scanning | ClamAV | Scan uploads before ingestion |
| Monitoring | Prometheus, Grafana | RAG and service observability |
| Migrations | Alembic | Versioned database schema changes |
| CI/Security | GitHub Actions, CodeQL, Trivy | Test and security gates |
| Deployment | Docker, Railway | Reproducible local/cloud deployment |

---

## Repository Structure

```text
intellivault-ai/
├── api.py                         # Production FastAPI application
├── dev_app.py                     # Docker-free development application
│
├── app/
│   ├── auth.py                    # JWT + Argon2 authentication
│   ├── config.py                  # Runtime configuration
│   ├── database.py                # SQLAlchemy database setup
│   ├── models.py                  # User / Document / Chunk models
│   ├── embeddings.py              # SentenceTransformer embeddings
│   ├── reranker.py                # Cross-Encoder reranking
│   ├── generator.py               # Ollama generation + streaming
│   ├── storage.py                 # S3-compatible storage adapter
│   ├── malware.py                 # ClamAV streaming scanner
│   ├── query_cache.py             # Redis cache
│   ├── celery_app.py              # Celery configuration
│   ├── tasks.py                   # PDF ingestion tasks
│   └── prometheus_metrics.py      # RAG metrics
│
├── frontend/                      # React/Vite frontend
├── tests/                         # Backend/security/storage tests
├── alembic/                       # Database migrations
├── monitoring/                    # Prometheus configuration
├── scripts/                       # Migration/repair utilities
├── railway/                       # Railway deployment edition
├── .github/                       # CI, security and repository config
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
├── pyproject.toml
├── SECURITY.md
└── .env.example
```

---

## Main Features

### Authentication & User Isolation

Users can register, sign in and access protected endpoints with bearer JWTs. Passwords are stored as Argon2 hashes. Document listing, deletion and retrieval are scoped to the authenticated user.

### Secure PDF Ingestion

The upload path includes multiple validation layers:

```text
Authenticated upload
      ↓
Rate limit
      ↓
Extension / size validation
      ↓
PDF signature + parser validation
      ↓
ClamAV scan
      ↓
Private S3-compatible storage
      ↓
Celery ingestion
```

Uploaded PDFs receive generated storage keys instead of being trusted as filesystem names.

### Asynchronous Processing

Production ingestion runs outside the HTTP request through Celery:

```text
Queued → Parsing → Embedding → Persisting → Ready
```

The frontend separately tracks network upload progress and server-side ingestion status.

### Streaming Answers

The frontend consumes `POST /query/stream` as newline-delimited JSON. It receives source metadata first, followed by partial answer fragments and final performance statistics.

Typical event sequence:

```json
{"type":"sources","sources":[...]}
{"type":"metrics","metrics":{"ttft_ms":742.1}}
{"type":"token","text":"IntelliVault "}
{"type":"token","text":"AI "}
{"type":"done","performance":{"total_ms":3112.4}}
```

### Latency Metrics

The application measures:

- embedding latency
- retrieval latency
- reranking latency
- time to first token (TTFT)
- generation latency
- stream duration
- total RAG latency
- streaming response-event rate

Prometheus histograms support aggregate production analysis such as P50/P95/P99.

---

## Docker-Free Development Mode

Want to explore the application without installing PostgreSQL, Redis, Celery, ClamAV, S3 or Ollama? Use the lightweight development server.

It substitutes:

```text
Production                       Docker-free development
────────────────────────────────────────────────────────
PostgreSQL + pgvector        →   SQLite
Private S3 bucket            →   Local dev storage
Redis + Celery               →   Synchronous processing
SentenceTransformer vectors  →   Lightweight lexical retrieval
Cross-Encoder                →   Lightweight score ordering
Ollama                       →   Simulated streaming generator
ClamAV                       →   PDF validation tests only
```

This mode is for development and demonstrations. It is not a performance or security equivalent of production.

### Start the backend

Windows PowerShell:

```powershell
python -m pip install -r requirements.txt
.\run_dockerfree.ps1
```

Linux/macOS:

```bash
python -m pip install -r requirements.txt
./run_dockerfree.sh
```

Backend:

```text
http://127.0.0.1:8000
```

Swagger:

```text
http://127.0.0.1:8000/docs
```

### Start the frontend

```bash
cd frontend
npm ci
npm run dev
```

Open:

```text
http://localhost:5173
```

---

## Run the Production Stack Locally

### Prerequisites

- Docker Desktop / Docker Engine with Compose
- Sufficient memory for the ML models and ClamAV
- Internet access on first startup for model downloads

### 1. Configure environment

```bash
cp .env.example .env
```

On PowerShell:

```powershell
Copy-Item .env.example .env
```

At minimum, replace development secrets before exposing the application publicly.

### 2. Start services

```bash
docker compose up -d --build
```

### 3. Apply database migrations

```bash
docker compose exec api alembic upgrade head
```

### 4. Check services

```bash
docker compose ps
```

Default development endpoints:

```text
Frontend      http://localhost:5173
FastAPI       http://localhost:8000
OpenAPI       http://localhost:8000/docs
Prometheus    http://localhost:9090
Grafana       http://localhost:3000
Ollama        http://localhost:11434
```

---

## Environment Configuration

Important production variables include:

```env
DATABASE_URL=postgresql+psycopg://...
JWT_SECRET_KEY=replace-with-a-long-random-secret
ACCESS_TOKEN_MINUTES=60
REDIS_URL=redis://...

GENERATION_MODEL=llama3.2:3b
OLLAMA_BASE_URL=http://ollama:11434

S3_ENDPOINT=https://your-s3-endpoint
S3_ACCESS_KEY_ID=replace
S3_SECRET_ACCESS_KEY=replace
S3_REGION=auto
S3_BUCKET=intellivault
S3_PREFIX=documents

CLAMAV_HOST=clamav
CLAMAV_PORT=3310
CLAMAV_FAIL_CLOSED=true

CORS_ORIGINS=https://your-frontend.example
TRUSTED_HOSTS=your-api.example
EXPOSE_DOCS=false
EXPOSE_METRICS=false
```

Never commit your real `.env` file. The repository `.gitignore` excludes secrets and runtime data.

---

## API Overview

| Endpoint | Method | Auth | Purpose |
|---|---|---|---|
| `/health` | GET | No | API health |
| `/auth/register` | POST | No | Create account |
| `/auth/login` | POST | No | Sign in |
| `/auth/me` | GET | Bearer | Current user |
| `/documents` | GET | Bearer | List owned documents |
| `/documents/upload` | POST | Bearer | Validate, scan and queue PDF |
| `/documents/{id}` | DELETE | Bearer | Delete owned document |
| `/jobs/{job_id}` | GET | Bearer | Ingestion progress |
| `/query` | POST | Bearer | Non-streaming RAG query |
| `/query/stream` | POST | Bearer | Streaming RAG query |
| `/metrics` | GET | Internal | Prometheus exposition |

Production deployments should keep operational metrics private.

---

## Testing and DevSecOps

### Run backend tests

```bash
pytest -q
```

The test suite includes coverage for areas such as:

- authentication behavior
- chunking
- S3 storage boundaries
- upload/download round trips
- optional live S3 smoke testing
- multi-page PDF extraction/retrieval
- PDF upload security validation
- migration and production components as extended

### Live S3 integration test

This is disabled by default so CI does not require cloud credentials.

```bash
RUN_S3_INTEGRATION=1 pytest -q tests/test_storage_s3_live.py
```

It uploads a small test PDF, verifies existence, downloads and compares the bytes, deletes it, and confirms deletion.

### Frontend

```bash
cd frontend
npm ci
npm run build
```

### GitHub Actions

The repository contains CI and security workflows covering:

- backend tests
- frontend build
- CodeQL for Python and JavaScript/TypeScript
- Python dependency auditing
- npm dependency auditing
- dependency review on pull requests
- Trivy filesystem/IaC/secret scanning
- Trivy container scanning
- Dependabot dependency updates

See `.github/GITHUB_SETTINGS.md` for recommended branch rules and repository security settings.

---

## Security Model

IntelliVault AI applies defense in depth, including:

- Argon2 password hashing
- signed JWT access tokens
- authenticated user-scoped database queries
- explicit CORS and trusted hosts
- security response headers
- upload size limits
- PDF extension/signature/parser validation
- generated storage keys
- ClamAV malware scanning
- fail-closed production scanning configuration
- private object storage
- API rate limiting
- non-root application container
- private database/Redis services
- optional disabling of Swagger/OpenAPI and Prometheus endpoints
- CI SAST, dependency, secret, IaC and container scanning

Read [`SECURITY.md`](SECURITY.md) before exposing the application to the Internet.

---

## Railway Deployment

A Railway-oriented deployment configuration is included under [`railway/`](railway/).

Recommended services:

```text
frontend                 PUBLIC
intellivault-api         PUBLIC
worker                   PRIVATE
pgvector                 PRIVATE
Redis                    PRIVATE
ClamAV                   PRIVATE
Ollama                   PRIVATE
S3-compatible bucket     PRIVATE
```

The API and worker both use the private S3-compatible bucket, which removes the need for a shared local filesystem and allows the two services to scale independently.

See [`railway/README.md`](railway/README.md) for the deployment steps and environment-variable templates.

---

## Verified Development Scenarios

The development test flow has been exercised for:

```text
✓ Account registration
✓ Successful login
✓ Invalid-password rejection
✓ Protected /auth/me request
✓ Single-page PDF upload
✓ Multi-page PDF upload
✓ PDF page counting
✓ PDF chunk generation
✓ Page-specific retrieval
✓ Source/page citations
✓ Streaming response events
✓ TTFT and total latency reporting
✓ S3 upload/download boundary tests
✓ PDF security validation tests
```

---

## Production Roadmap

Potential next improvements:

- server-sent events (SSE) or WebSocket transport where operationally useful
- distributed Redis-backed per-user/API rate limiting
- dedicated GPU inference service
- recall@K / MRR retrieval-quality evaluation suite
- OCR for scanned/image-only PDFs
- Content Disarm & Reconstruction for higher-risk uploads
- organization/tenant knowledge bases
- audit events and administrator controls
- database connection pooling
- model and prompt evaluation pipelines
- Kubernetes only when operational scale justifies it

---

## GitHub Repository Setup

Recommended repository slug:

```text
intellivault-ai
```

Project/display name:

```text
IntelliVault AI
```

Suggested GitHub topics:

```text
rag
retrieval-augmented-generation
fastapi
react
pgvector
postgresql
redis
celery
ollama
sentence-transformers
s3
railway
prometheus
grafana
docker
devsecops
ai
nlp
bilingual
```

Detailed repository settings are available in `.github/GITHUB_SETTINGS.md`.

---

## Author

**Vishal Kumar Sharma**  
M.Tech in Computer Science & Engineering

---

## Project Status

**Version:** `1.0.0`  
**Status:** Active development / production-oriented portfolio release  
**Primary language:** Python + JavaScript  
**Interface:** English / Hindi

---

<div align="center">

### IntelliVault AI

**Turn private documents into secure, searchable, source-grounded knowledge.**

</div>
