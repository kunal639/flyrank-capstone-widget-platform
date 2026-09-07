# FlyRank Widget Platform

An embeddable lead capture widget platform built with FastAPI, SQLAlchemy, and vanilla JavaScript.

---

## Architecture Overview

The system operates across two distinct surfaces:

```text
Customer Website (Port 3000)                FlyRank Backend (Port 8000)
       │                                                 │
       │ <script data-widget-id="...">                   │
       ├────────────── GET /widgets/{id}/config ────────>│ (Public Schema)
       │                                                 │
       │ Form Rendered Dynamically                       │
       │                                                 │
       ├────────────── POST /submissions ───────────────>│ (CORS / Honeypot / Rate Limit)
                                                         ├── Database Commit (Atomic)
                                                         │    ├── Submission
                                                         │    ├── Field Values
                                                         │    └── Notification Outbox
                                                         │
Tenant Dashboard (/dashboard)                            └── Background Worker (app.worker)
       │                                                      │
       └────────────── GET /submissions ──────────────────────┘
                       (Scoped to Bearer Token)
```

## Prerequisites

- Python 3.11+
- [`uv`](https://docs.astral.sh/uv/) package manager
- PostgreSQL service running locally (native install or Docker)

---

## Quick Setup

### 1. Clone and Install Dependencies

```bash
git clone <repository-url>
cd flyrank-capstone-widget-platform
uv sync
```

### 2. Configure Environment & Database

Create your local PostgreSQL database (e.g., via `psql` or pgAdmin):

```sql
CREATE DATABASE widget_platform;
```

Copy the environment template and ensure your PostgreSQL user, password, port, and database name match:

```bash
cp .env.example .env
```

Example connection string inside `.env`:

```
DATABASE_URL=postgresql://postgres:your_password@localhost:5432/widget_platform
```

### 3. Run Database Migrations

```bash
uv run alembic upgrade head
```

---

### Check Database Service Status (Windows PowerShell)

To confirm your local Windows PostgreSQL service is active:

```powershell
Get-Service -Name postgres*
```

If it is stopped, start it with:

```powershell
Start-Service -Name postgresql*
```

## Running the Services

### 1. Start the API Server

```bash
uv run uvicorn app.main:app --reload --port 8000
```

- API Root: `http://localhost:8000`
- Interactive Docs: `http://localhost:8000/docs`
- Tenant Dashboard: `http://localhost:8000/dashboard/`

### 2. Start the Notification Outbox Worker (Separate Terminal)

```bash
uv run python -m app.worker
```

## Testing & Quality Assurance

Run the complete test suite:

```bash
uv run pytest -q
```

Run evaluator-specific end-to-end tests:

```bash
uv run pytest tests/test_capstone_evaluator.py -v
```

## End-to-End Demonstration Walkthrough

Follow these steps to demonstrate the full lifecycle:

1. **Obtain Test Tenant Token:**

   ```bash
   uv run python -c "from app.db.session import SessionLocal; from app.models.tenant import Tenant; db = SessionLocal(); print(db.query(Tenant).first().tenant_id); db.close()"
   ```

2. **Open Tenant Dashboard:**
   - Visit `http://localhost:8000/dashboard/`.
   - Paste the UUID into the Tenant Token input on the sidebar.

3. **Configure a Widget:**
   - In the dashboard, click **Fields** on an existing widget (or create a new one).
   - Update field order, toggle required attributes, and click **Save Configuration**.
   - Note the `Widget ID`.

4. **Run Cross-Origin Embed Demo:**
   - In `frontend/demo/index.html`, ensure the script tag contains your active `Widget ID`.
   - In a new terminal, serve the demo site from a different port:

     ```bash
     uv run python -m http.server 3000 --directory frontend/demo
     ```

   - Open `http://localhost:3000` in your browser.

5. **Submit Lead:**
   - Fill out the dynamic form and click **Submit**.
   - Observe the success message and verify the submission appears in the Tenant Dashboard under the **Submissions** tab.