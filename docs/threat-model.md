# Threat Model & Security Architecture

## Overview

The FlyRank Widget Platform operates a dual-boundary model:
1. **Authenticated Management APIs:** Private endpoints reserved for tenants to manage widgets, configure field schemas, and inspect lead submissions.
2. **Public Widget Endpoints:** Internet-facing endpoints exposed to arbitrary web clients to fetch rendering schemas and record lead submissions.

This document outlines the threat landscape, potential attack vectors, mitigations, and architectural boundaries enforced across the platform.

---

## Threat Matrix

| Threat Category | Attack Vector | System Impact | Mitigation / Architectural Control |
|---|---|---|---|
| **Cross-Tenant IDOR** | Manipulating UUID parameters (e.g. `GET /submissions/{id}`) | Unauthorized access to another tenant's confidential leads | Identity derived exclusively from auth credentials (`get_current_tenant`). Database queries join through `tenant_id`. Cross-tenant lookups return `404 Not Found`. |
| **Client Spoofing** | Attacker passes `{"tenant_id": "victim-uuid"}` in request body | Privilege escalation or resource modification | Authenticated request schemas forbid client-provided tenant identifiers. The tenant context is non-configurable by client input. |
| **Duplicate / Replay Attacks** | Network retry storms or intentional submission replays | Redundant lead entries, duplicate notification triggers | Server enforces database-level uniqueness constraint `UNIQUE(widget_id, idempotency_key)`. Replays return `409 Conflict`. |
| **Spam / Automated Bots** | Headless scripts submitting garbage data | Database pollution, alert flooding | Invisible honeypot field. If populated, request aborts immediately with `422 Unprocessable Content` with zero DB persistence. |
| **DoS via Large Payloads** | Massive JSON payloads (> 64 KiB) to exhaust memory | Worker starvation / buffer overflow | Streaming HTTP middleware verifies `Content-Length` and enforces payload truncation limit at 64 KiB (`413 Payload Too Large`). |
| **Burst Flooding** | High-frequency automated calls to `POST /submissions` | Database connection pool exhaustion | In-memory sliding-window rate limiter (10 requests per 60 seconds per client IP and widget) returning `429 Too Many Requests`. |
| **Origin Hijacking** | Malicious third-party embedding client's widget script | Unauthorized lead collection from unapproved domains | Server checks the `Origin` header against `widget.allowed_origins`. Disallowed origins return `403 Forbidden` without CORS headers. |
| **External Geo Outage** | IP enrichment provider down, hanging, or slow | Delayed submission processing or submission failures | Tiered fallback chain (`ip-api.com` → `ipapi.co`) with strict timeouts. Failures degrade gracefully to `NULL` without blocking submission commit. |
| **Notification Failure** | Tenant webhook/email endpoint offline | Lost leads or failed HTTP request rollback | Transactional Outbox pattern. Submissions commit atomically with an outbox record; asynchronous worker retries delivery independently. |
| **SQL / Code Injection** | Malicious characters in form fields | Unauthorized DB operations or data corruption | SQLAlchemy parameterized queries across all database operations. Strict type validation per field definition (`text`, `email`, `number`, `boolean`). |
| **Information Leakage** | Triggering internal server errors to inspect stack traces | Unveiling filesystem paths, library versions, DB schemas | FastAPI error sanitization and structured error schemas. Direct exception traces (`str(e)`) suppressed from public API responses. |
| **Secret Exfiltration** | Accidental commit of `.env` files or API credentials | Compromise of production keys and databases | `.env*` excluded via `.gitignore`. `.env.example` verified to contain dummy values only. |

---

## Defense-in-Depth Pipeline (`POST /submissions`)

Every public submission flows through an ordered sequence of protective layers before touching the database:

```text
Incoming Request
       │
       ▼
[ Layer 1: Body Size Verification ] ─────────> Exceeds 64 KiB ──> 413 Payload Too Large
       │
       ▼
[ Layer 2: Pydantic Schema Parsing ] ────────> Invalid types ────> 422 Unprocessable Content
       │
       ▼
[ Layer 3: Widget Origin Boundary ] ─────────> Unlisted origin ──> 403 Forbidden
       │
       ▼
[ Layer 4: Sliding Window Rate Limit ] ──────> Exceeds quota ───> 429 Too Many Requests
       │
       ▼
[ Layer 5: Honeypot Anti-Spam Check ] ───────> Non-empty trap ──> 422 Unprocessable Content
       │
       ▼
[ Layer 6: Dynamic Field Schema Validation ] ─> Missing req fields > 422 Unprocessable Content
       │
       ▼
[ Layer 7: Non-Blocking Geo Enrichment ] ────> Provider failure ─> Degrades to NULL (proceeds)
       │
       ▼
[ Layer 8: Atomic Transaction Commit ] ──────> Duplicate key ────> 409 Conflict
       │
       ├── Persist Submission
       ├── Persist SubmissionFieldValues
       └── Persist NotificationOutbox
       │
       ▼
201 Created (with Access-Control-Allow-Origin)