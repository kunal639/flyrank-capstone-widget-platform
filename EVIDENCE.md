# Evaluator Evidence Matrix

This document provides a direct mapping between the core architectural and security requirements of the FlyRank Widget Platform capstone, their exact codebase implementations, and automated/manual proof.

---

## Requirement to Implementation & Proof Mapping

| Requirement | Implementation Details | Verification & Proof |
|---|---|---|
| **Authenticated CRUD** | `app/api/widgets.py`<br>`app/api/widget_fields.py` | `tests/test_api_widgets.py`<br>`tests/test_api_widget_fields.py`<br>`tests/test_capstone_evaluator.py::test_evaluator_complete_end_to_end_lifecycle` |
| **Strict Tenant Isolation** | `app/auth/dependencies.py` (`get_current_tenant`)<br>`app/api/submissions.py` (`_tenant_submission_query`) | `tests/test_security_audit.py::test_idor_cannot_modify_other_tenant_widget`<br>`tests/test_capstone_evaluator.py::test_evaluator_cross_tenant_isolation_boundary` |
| **Public Configuration API** | `GET /widgets/{widget_id}/config` in `app/api/widgets.py` | `tests/test_api_widgets.py::test_get_public_widget_config`<br>`tests/test_security_audit.py::test_public_config_does_not_leak_tenant_id_or_secrets` |
| **Cross-Origin & Preflight Submission** | `OPTIONS` & `POST /submissions` in `app/api/submissions.py`<br>Origin header checked against `widget.allowed_origins` | `tests/test_capstone_evaluator.py::test_evaluator_second_origin_success`<br>`tests/test_capstone_evaluator.py::test_evaluator_disallowed_origin_rejection` |
| **Malformed Payload Handling** | Pydantic validation via `app/schemas/submission.py` and dynamic field schema checks in `app/api/submissions.py` | `tests/test_capstone_evaluator.py::test_evaluator_malformed_payload_returns_json_4xx` |
| **Oversized Payload Protection** | Streaming HTTP middleware in `app/main.py` (`limit_public_submission_size`) checking `MAX_PUBLIC_SUBMISSION_BYTES` | `tests/test_capstone_evaluator.py::test_evaluator_oversized_payload_returns_413_and_recovers` |
| **Sliding-Window Rate Limiting** | `app/rate_limit.py` (`SlidingWindowRateLimiter`) evaluated on `(widget_id, client_ip)` returning `429 Too Many Requests` | `tests/test_rate_limit.py`<br>`tests/test_api_submissions.py::test_submission_rate_limiting` |
| **Honeypot Anti-Spam Control** | Hidden input check in `app/api/submissions.py` (`payload.honeypot != ""` $\rightarrow$ `422 Unprocessable Content`) | `tests/test_capstone_evaluator.py::test_evaluator_honeypot_triggers_422_with_zero_side_effects` |
| **Geo Enrichment & Fallback** | `app/geo.py` with ordered providers (`IpApiProvider` $\rightarrow$ `IpApiCoProvider`). Non-blocking failure defaults to `NULL` | `tests/test_geo.py`<br>`tests/test_capstone_evaluator.py::test_evaluator_geo_fallback_chain` |
| **Transactional Outbox & Worker Retries** | `app/repositories/submission.py`<br>`app/models/notification_outbox.py`<br>`app/worker.py` | `tests/test_capstone_evaluator.py::test_evaluator_notification_failure_does_not_abort_submission`<br>`tests/test_capstone_evaluator.py::test_evaluator_notification_worker_retries_and_terminal_failure` |
| **Idempotency (Per-Widget)** | Database unique constraint `uq_submission_widget_id_idempotency_key` on `submission` table | `tests/test_capstone_evaluator.py::test_evaluator_idempotency_is_scoped_per_widget` |
| **Atomic Persistence** | `SubmissionRepository.create_submission_with_values` creates `Submission`, `SubmissionFieldValue`, and `NotificationOutbox` in a single transaction | `tests/test_capstone_evaluator.py::test_evaluator_database_persistence_and_atomicity` |
| **Embeddable JavaScript Client** | `frontend/widget/widget.js`<br>`frontend/widget/widget.css` | `frontend/demo/index.html`<br>Manual cross-origin browser verification on separate port (3000 $\rightarrow$ 8000) |
| **Tenant Management Dashboard** | `frontend/dashboard/index.html`<br>`frontend/dashboard/app.js`<br>`frontend/dashboard/app.css` | Accessible at `/dashboard/`. Verified CRUD, field reordering/toggles, submission inspector, and auth token resets |