# Engineering Build Log & AI Collaboration Audit

## Overview
This platform was developed using an iterative, commit-by-commit engineering methodology. Large Language Models (LLMs) were utilized as technical thought partners, code generators, and test design assistants.

---

## 1. Where AI Assisted Effectively
* **Architecture Brainstorming:** Formulating the dual-boundary design separating public widget endpoints from tenant-scoped management APIs.
* **Test Case Generation:** Translating adversarial test requirements (e.g. rate-limit sliding windows, second-origin preflight checks, and outbox failure loops) into `pytest` suites.
* **Schema Definition:** Drafting SQLAlchemy 2.0 type-annotated models and Pydantic validation schemas.
* **Frontend Scaffolding:** Generating the vanilla embeddable JavaScript widget client and Tailwind-powered tenant dashboard with zero external bundler dependencies.

---

## 2. Where AI Was Wrong & How It Was Resolved
* **CORS Middleware Conflict (Commit 16):**
  * *AI Suggestion:* Recommended attaching generic Starlette `CORSMiddleware` with `allow_origins=["*"]` to resolve browser preflight errors during demo testing.
  * *Problem:* Overrode fine-grained origin checks. Requests with disallowed origins still received wildcard CORS headers, and preflight `OPTIONS` returned `200 OK` instead of the mandated `204 No Content`, failing 6 unit tests.
  * *Correction:* Removed generic `CORSMiddleware`. Restored fine-grained origin validation and explicit response header assignment inside route handlers.
* **Import Path Assumptions in Evaluator Tests (Commit 18):**
  * *AI Suggestion:* Generated tests patching `app.services.geo_service.GeoService.lookup_ip`.
  * *Problem:* The codebase organizes geo enrichment under `app.geo.GeoEnricher` instantiated in `app.api.submissions.geo_enricher`. The patch caused an `AttributeError: module 'app' has no attribute 'services'`.
  * *Correction:* Inspected actual module bindings and patched `app.api.submissions.geo_enricher.enrich`.
* **Database Model Attribute Discrepancy (Commit 18):**
  * *AI Suggestion:* Attempted to access `SubmissionFieldValue.field_name` directly in persistence assertions.
  * *Problem:* Schema normalizes field metadata through `WidgetField` and `FieldDefinition`. `SubmissionFieldValue` stores `widget_field_id`.
  * *Correction:* Updated assertions to traverse `v.widget_field.field_definition.field_name`.

---

## 3. Personal Verification & Code Ownership
* **Test Execution:** Ran the complete test suite (`uv run pytest -q`) after every commit to verify that new features caused zero regressions.
* **Browser Runtime Verification:** Manually verified cross-origin request lifecycles between separate localhost origins (`http://localhost:3000` to `http://localhost:8000`).
* **Security & Invariants:** Verified that tenant isolation is enforced at the database layer through parameterized queries and user token derivation rather than client parameters.