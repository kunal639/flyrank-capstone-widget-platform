# API Contracts

## Overview

The API has two main categories:

1. **Authenticated management and dashboard APIs** — used by logged-in customers
2. **Public widget APIs** — used by embedded widgets on visitor-facing websites

Authenticated APIs are always scoped to the logged-in tenant (customer).

Public submission APIs are open to embedded widgets, but they're protected by origin checks, validation, rate limiting, and spam controls.

> **Note:** This document is our proposed API contract based on the design decisions we've made — it's not something dictated word-for-word by any spec. It's meant to be a clear reference for what we're building, not a frozen, unchangeable spec (more on that at the end).

---

## Authentication

Authenticated endpoints require the caller to be a logged-in customer.

The tenant context always comes from who is authenticated — **never** from something the client sends in the request. In other words, we never just trust a `tenant_id` value handed to us in a request body; it has to be derived from the authenticated identity.

```text
Authenticated Request
        |
        v
Authenticated Identity
        |
        v
Tenant Context
        |
        v
Tenant-scoped Resource
```

---

## Widget Management

### Create Widget

`POST /widgets`

Creates a new widget for the logged-in tenant.

**Request**
```json
{
  "widget_type_id": "uuid",
  "title": "Contact Us",
  "allowed_origins": [
    "https://example.com"
  ]
}
```

**Response**
```
201 Created
{
  "widget_id": "uuid",
  "widget_type_id": "uuid",
  "title": "Contact Us",
  "allowed_origins": [
    "https://example.com"
  ]
}
```

### List Widgets

`GET /widgets`

Returns all widgets that belong to the logged-in tenant.

**Response**
```
200 OK
{
  "widgets": [
    {
      "widget_id": "uuid",
      "widget_type_id": "uuid",
      "title": "Contact Us"
    }
  ]
}
```

### Get Widget

`GET /widgets/:widget_id`

Returns one widget — but only if it belongs to the logged-in tenant. A widget owned by a different tenant should never be returned.

**Response:** `200 OK`

### Update Widget

`PATCH /widgets/:widget_id`

Updates a widget owned by the logged-in tenant.

**Request**
```json
{
  "title": "Contact Support",
  "allowed_origins": [
    "https://example.com",
    "https://app.example.com"
  ]
}
```

**Response:** `200 OK`

### Delete Widget

`DELETE /widgets/:widget_id`

Deletes a widget owned by the logged-in tenant.

**Response:** `204 No Content`

---

## Widget Fields

### Configure Widget Fields

`PUT /widgets/:widget_id/fields`

Sets which fields a widget uses.

**Request**
```json
{
  "fields": [
    {
      "field_id": "uuid",
      "display_order": 1,
      "required": true
    },
    {
      "field_id": "uuid",
      "display_order": 2,
      "required": false
    }
  ]
}
```

**This endpoint should reject:**
- fields that don't exist
- the same field listed twice on one widget
- two fields with the same display order
- invalid field settings
- any attempt to modify a widget that belongs to a different tenant

---

## Public Widget Configuration

### Get Widget Configuration

`GET /widgets/:widget_id/config`

Returns the public settings the embedded widget needs to render itself. This response should never leak any private tenant information.

**Response**
```
200 OK
{
  "widget_id": "uuid",
  "widget_type": "contact",
  "title": "Contact Us",
  "fields": [
    {
      "field_id": "uuid",
      "name": "email",
      "type": "email",
      "required": true
    },
    {
      "field_id": "uuid",
      "name": "message",
      "type": "text",
      "required": true
    }
  ]
}
```

This endpoint's responses should be cacheable where it makes sense, since the same config gets fetched repeatedly by every visitor.

---

## Public Submission

### Create Submission

`POST /submissions`

Receives a submission from an embedded widget, tied to a specific widget.

**Request**
```json
{
  "idempotency_key": "client-generated-key",
  "visitor_email": "visitor@example.com",
  "fields": {
    "email": "visitor@example.com",
    "message": "Hello"
  }
}
```

**What happens along the way:**

```text
CORS / Origin Check
        |
        v
Request Validation
        |
        v
Rate Limiting
        |
        v
Spam Protection
        |
        v
Geo Enrichment
        |
        v
Database Transaction
```

The database transaction saves:
- the submission
- the individual submitted field values
- a notification outbox event

**On success**
```
201 Created
{
  "submission_id": "uuid"
}
```

Importantly, the response to the visitor should never depend on whether the notification was sent successfully — that happens separately, afterward.

### Idempotency

This endpoint accepts an idempotency key so the same request can't accidentally create duplicate submissions.

- `submission_id` is still the true identity of the submission.
- The idempotency key is only used to spot duplicates.
- The rule enforced is: `UNIQUE(widget_id, idempotency_key)`
- Sending the same idempotency key twice should never create two submissions.

### CORS and Origin Handling

This endpoint supports cross-origin requests from browsers.

- Preflight requests use `OPTIONS /submissions`.
- The API should respond correctly for allowed origins.
- If a widget has specific allowed origins configured, requests from any other origin must be rejected.
- A widget is also allowed to have no origin restrictions configured at all.

### Validation Errors

Bad requests get a proper `4xx` response — never a generic server error.

**Example**
```
400 Bad Request
{
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "Invalid submission",
    "fields": {
      "email": "Invalid email address"
    }
  }
}
```

The exact error codes used can be finalized while building it.

### Rate Limiting

The public submission endpoint has rate limiting.

When someone goes over the limit:
```
429 Too Many Requests
{
  "error": {
    "code": "RATE_LIMITED",
    "message": "Too many requests"
  }
}
```

Once the rate-limit window passes, normal requests should be able to succeed again.

---

## Dashboard

All dashboard endpoints require authentication, and every resource returned is scoped to the logged-in tenant.

### List Submissions

`GET /submissions`

Returns submissions belonging to the logged-in tenant. Filtering options can be added later as needed.

### Get Submission

`GET /submissions/:submission_id`

Returns a submission — only if it belongs to the logged-in tenant.

### Widget Submission Statistics

`GET /widgets/:widget_id/stats`

Returns basic stats for a widget.

**Example**
```json
{
  "total_submissions": 1250,
  "submissions_over_time": [
    {
      "date": "2026-08-01",
      "count": 42
    }
  ]
}
```

### Geo Statistics

`GET /widgets/:widget_id/stats/geo`

Returns a breakdown of submissions by location, where that data is available. Missing location data should never cause this request to fail.

---

## Notification Processing

Notifications are handled asynchronously, in the background — they're not part of the public submission API.

Creating a submission also creates a piece of notification work, which a background worker later picks up and processes.

```text
POST /submissions
        |
        v
Database Transaction
        |
        v
Notification Outbox
        |
        v
Background Worker
        |
        v
Notification Provider
```

A failed notification should never undo or invalidate a submission that's already been saved. The worker retries a limited number of times and records the final outcome.

---

## HTTP Status Codes

| Status | Meaning |
|---|---|
| 200 | Successful request |
| 201 | Resource successfully created |
| 204 | Successful request, nothing to return |
| 400 | Invalid request |
| 401 | Authentication required |
| 403 | Request not allowed |
| 404 | Resource not found |
| 409 | Conflict / duplicate request |
| 429 | Too many requests (rate limited) |
| 500 | Unexpected server error |

The exact status code for a duplicate idempotent request will be finalized during implementation.

---

## Tenant Isolation

Every authenticated endpoint must figure out the tenant from the authenticated identity — never from a value the client provides directly.

**Not allowed:**
```text
request.tenant_id
        |
        v
trust tenant
```

**Correct approach:**
```text
authenticated identity
        |
        v
resolved tenant
        |
        v
tenant-scoped query
```

Every query involving a widget, submission, or dashboard data must check that it belongs to the right tenant.

---

## API Design Principles

- Public submission APIs should keep working even when non-critical outside services fail.
- Authenticated resources are always scoped to a tenant.
- Validation failures return clean `4xx` responses.
- Idempotency prevents duplicate submissions from being saved.
- A notification failure should never block a submission from being saved successfully.
- Public widget configuration should only expose what the widget actually needs — nothing more.
