# CQC Readiness

A production-ready daily CQC readiness check system for Bristol Care Homes.

Every working day, care home managers and deputy managers receive a personalised
email containing a "We Statement" from the CQC key question framework. They answer
three quick confidence questions via button links in the email. Low-confidence
responses automatically trigger a support pack and alert the Care Quality Manager.

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         cqc-readiness System                                 │
│                                                                              │
│  ┌──────────────────┐     ┌─────────────────────────────────────────────┐  │
│  │   APScheduler     │     │              FastAPI App                    │  │
│  │  (Mon–Fri 07:00)  │────▶│  GET /respond/{token}/q/{num}/{answer}      │  │
│  │                  │     │  GET /admin/dashboard                        │  │
│  └──────────────────┘     │  GET /admin/alerts                          │  │
│           │               │  POST /admin/alerts/{id}/resolve             │  │
│           ▼               │  GET /health                                 │  │
│  ┌──────────────────┐     └──────────────┬──────────────────────────────┘  │
│  │  Assignment Svc  │                    │                                  │
│  │  (round-robin    │                    ▼                                  │
│  │   per role)      │     ┌─────────────────────────────────────────────┐  │
│  └──────────────────┘     │     PostgreSQL (SQLAlchemy async)            │  │
│           │               │  we_statements / recipients                  │  │
│           ▼               │  daily_assignments / responses / cqm_alerts  │  │
│  ┌──────────────────┐     └─────────────────────────────────────────────┘  │
│  │   Email Service  │                                                       │
│  │  (Graph API)     │     ┌─────────────────────────────────────────────┐  │
│  │                  │     │        Jinja2 HTML Templates                 │  │
│  │  daily_check.html│     │  email/  daily_check, support_pack, alert   │  │
│  │  support_pack.html│◀───│  web/   answer_recorded, complete, expired   │  │
│  │  cqm_alert.html  │     │         admin/dashboard, admin/alerts        │  │
│  └──────────────────┘     └─────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────────────┘

Azure deployment:
  App Service (Python 3.12) + PostgreSQL Flexible Server + Key Vault + App Insights
```

---

## Local Development with Docker Compose

### Prerequisites
- Docker Desktop
- Python 3.12 (for running seed scripts / tests locally)

### 1. Generate an admin password hash

```bash
python -c "from passlib.context import CryptContext; print(CryptContext(schemes=['bcrypt']).hash('your-password'))"
```

Copy the output hash.

### 2. Configure environment

Create a `.env` file (used locally, never committed):

```env
DATABASE_URL=postgresql+asyncpg://cqc:devpassword@localhost:5432/cqc_readiness
GRAPH_TENANT_ID=your-azure-ad-tenant-id
GRAPH_CLIENT_ID=your-app-registration-client-id
GRAPH_CLIENT_SECRET=your-client-secret
GRAPH_SENDER_EMAIL=noreply@yourdomain.com
CQM_ALERT_EMAIL=cqm@yourdomain.com
APP_BASE_URL=http://localhost:8000
ADMIN_USERNAME=admin
ADMIN_PASSWORD_HASH=$2b$12$...your-hash-here...
SCHEDULER_SEND_HOUR=7
SCHEDULER_TIMEZONE=Europe/London
TOKEN_EXPIRY_HOURS=16
```

Update `docker-compose.yml` with the same values.

### 3. Start the stack

```bash
docker-compose up -d
```

### 4. Run database migrations

```bash
docker-compose exec app alembic upgrade head
```

### 5. Seed data

```bash
# Seed the 30 We Statements
docker-compose exec app python -m app.seed.we_statements

# Seed placeholder recipients
docker-compose exec app python -m app.seed.recipients
```

### 6. Verify

- App: http://localhost:8000/health
- Admin dashboard: http://localhost:8000/admin/dashboard (admin / your-password)
- API docs: http://localhost:8000/docs

---

## Azure Deployment with `azd up`

### Prerequisites
- [Azure Developer CLI (azd)](https://learn.microsoft.com/en-us/azure/developer/azure-developer-cli/install-azd)
- Azure subscription with Contributor rights
- Azure AD App Registration (see below)

### 1. Log in

```bash
azd auth login
az login
```

### 2. Set sensitive parameters in a bootstrap Key Vault

Before deploying, create a Key Vault and store these secrets:

| Secret name          | Value                          |
|----------------------|--------------------------------|
| `db-admin-password`  | Strong random password         |
| `graph-tenant-id`    | Azure AD tenant ID             |
| `graph-client-id`    | App registration client ID     |
| `graph-client-secret`| App registration client secret |
| `admin-password-hash`| bcrypt hash (see above)        |

Update `infra/parameters.json` with your subscription ID, resource group, and bootstrap Key Vault name.

### 3. Deploy

```bash
azd up
```

This runs `azd provision` (deploys Bicep) then `azd deploy` (publishes the app).

### 4. Run migrations in Azure

```bash
az webapp ssh --name cqcreadiness-app --resource-group <your-rg>
# Inside the shell:
alembic upgrade head
python -m app.seed.we_statements
python -m app.seed.recipients
```

---

## Azure AD App Registration Setup

1. Go to **Azure Portal → Azure Active Directory → App registrations → New registration**
2. Name: `CQC Readiness Mailer`
3. Supported account types: **Accounts in this organizational directory only**
4. No redirect URI needed (daemon app)
5. After creation, note:
   - **Application (client) ID** → `GRAPH_CLIENT_ID`
   - **Directory (tenant) ID** → `GRAPH_TENANT_ID`
6. Go to **Certificates & secrets → New client secret** → copy the value → `GRAPH_CLIENT_SECRET`
7. Go to **API permissions → Add a permission → Microsoft Graph → Application permissions**
   - Add: `Mail.Send`
8. Click **Grant admin consent**
9. Set `GRAPH_SENDER_EMAIL` to a mailbox in your tenant that this app is allowed to send from

---

## How to Add We Statements

### Option A — Edit the seed file and re-run

Edit `app/seed/we_statements.py`, add a new entry to `WE_STATEMENTS_DATA`, then run:

```bash
python -m app.seed.we_statements
```

The script is idempotent — existing statements are skipped.

### Option B — SQL

```sql
INSERT INTO we_statements
  (key_question, role_group, statement_text, evidence_types,
   guidance_notes, inspection_tips, sort_order, is_active)
VALUES
  ('Safe', 'manager', 'Your statement text here',
   '["Evidence A", "Evidence B"]',
   'Guidance notes here.',
   'Inspection tip here.',
   31, true);
```

---

## How to Add Recipients

### Option A — Edit the seed file and re-run

Edit `app/seed/recipients.py`, add entries, then:

```bash
python -m app.seed.recipients
```

### Option B — SQL

```sql
INSERT INTO recipients (full_name, email, role, home_name, is_active)
VALUES ('Jane Smith', 'jane@example.com', 'HomeManager', 'Oak House', true);
```

**Valid role values:** `HomeManager`, `DeputyManager`, `OperationsManager`, `CareQualityManager`

- `HomeManager` and `OperationsManager` receive **manager** and **all** group statements
- `DeputyManager` receives **deputy** and **all** group statements
- `CareQualityManager` receives **no daily check emails** (they only receive CQM alerts)

---

## Admin Dashboard

**URL:** `/admin/dashboard`

**Credentials:** Set via `ADMIN_USERNAME` and `ADMIN_PASSWORD_HASH` environment variables.

To generate a password hash:

```bash
python -c "
from passlib.context import CryptContext
pwd = CryptContext(schemes=['bcrypt'])
print(pwd.hash('your-secure-password'))
"
```

The dashboard shows:
- Completion rate for the current week
- Confidence breakdown by CQC key question (last 30 days)
- Open alerts grouped by care home
- Top 5 weakest We Statements
- Last 20 completions

**Alerts page:** `/admin/alerts` — filter, view, resolve, and export alerts to CSV.

---

## Scheduler Timezone Note

The daily job fires at `SCHEDULER_SEND_HOUR` (default: 07:00) in
`SCHEDULER_TIMEZONE` (default: `Europe/London`).

The timezone correctly accounts for BST/GMT transitions.
Tokens are valid only on the **calendar day** they were issued in the same timezone —
so a token sent at 07:00 on Monday expires at midnight UK time on Monday.

If the app restarts after the scheduled time, APScheduler's `misfire_grace_time`
(1 hour) allows the job to run up to 1 hour late.  The job is also idempotent —
recipients who already have an assignment for the day will not receive duplicates.

---

## Running Tests

```bash
pip install -r requirements.txt
pytest tests/ -v
```

Tests use an in-memory SQLite database via `aiosqlite` — no PostgreSQL required.
