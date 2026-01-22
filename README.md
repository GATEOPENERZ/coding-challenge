# Multi-Tenant Invoice Reconciliation API

A production-grade, Async Python API for reconciling invoices with bank transactions, featuring strict multi-tenant isolation, idempotency, and AI-powered match explanations.

## Stack

-   **Language:** Python 3.13
-   **Web Framework:** FastAPI (REST) & Strawberry (GraphQL)
-   **ORM:** SQLAlchemy 2.0 (Async)
-   **Database:** SQLite (Async via aiosqlite) for portability, easy to swap for Postgres.
-   **Testing:** Pytest with pytest-asyncio

## Setup & Running

1.  **Install Dependencies:**
    ```bash
    pip install .[test]
    ```

2.  **Run the Server:**
    ```bash
    uvicorn app.main:app --reload
    ```
    -   REST Docs: http://localhost:8000/docs
    -   GraphQL Playground: http://localhost:8000/graphql

3.  **Run Tests:**
    ```bash
    pytest -v
    ```

## Key Design Decisions

### 1. Multi-Tenancy Strategy

I implemented "Row-Level Security" at the application layer:

-   **Database:** All tables (except `tenants`) have a `tenant_id` foreign key with an index for performance.
-   **Service Layer:** Every database query filters strictly by `tenant_id`.
-   **API Layer:** All endpoints are tenant-scoped via path parameter (`/tenants/{tenant_id}/...`).
-   **Isolation Guarantee:** Tenant A cannot view or manipulate Tenant B's data.

### 2. Idempotency Implementation

The `POST /bank-transactions/import` endpoint is fully idempotent:

-   **Mechanism:** Dedicated `idempotency_keys` table stores the key, payload hash, and response.
-   **Flow:**
    1.  Hash the incoming payload using SHA-256.
    2.  If the key exists with matching hash → return cached response (no reprocessing).
    3.  If the key exists with different hash → return `409 Conflict`.
    4.  If new key → lock, process, store result, return.
-   **Race Condition Handling:** Uses database-level unique constraint with retry logic for concurrent requests.

### 3. Reconciliation Scoring Logic

The reconciliation engine uses a **deterministic weighted heuristic** approach (Score 0.0 - 1.0) to rank matches **without relying on AI**:

| Factor | Weight | Criteria |
|--------|--------|----------|
| **Amount Match** | 0.6 (60%) | Exact match if `abs(invoice.amount - tx.amount) < 0.01` AND currencies match |
| **Date Proximity** | 0.2 (20%) | Within 3 days: +0.2, Within 7 days: +0.1 |
| **Text Similarity** | 0.2 (20%) | Uses `difflib.SequenceMatcher` ratio between invoice description and transaction memo |

**Scoring Formula:**
```
score = (amount_match * 0.6) + (date_score * 0.2) + (text_similarity * 0.2)
```

**Threshold:** Only candidates with `score > 0.3` are returned, sorted descending by score.

**Design Rationale:** 
- Amount is weighted highest because financial matching requires exact amounts.
- Date proximity helps disambiguate when multiple transactions have similar amounts.
- Text similarity provides additional context matching for invoices with descriptions.

### 4. AI Integration (Pragmatic Approach)

-   **Purpose:** Generate natural-language explanations for match decisions.
-   **Endpoint:** `GET /tenants/{tenant_id}/reconcile/explain?invoice_id=...&transaction_id=...`
-   **Configuration:** `AI_API_URL` environment variable (defaults to Pollinations API).
-   **Resilience:** Wrapped in try/except with graceful fallback:
    -   If AI errors/timeouts/unavailable → returns deterministic explanation based on heuristics.
-   **Security:** Only tenant-authorized data (amounts, dates, descriptions) is sent to AI.

## API Reference

### REST Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/v1/tenants` | Create tenant |
| GET | `/api/v1/tenants` | List all tenants |
| POST | `/api/v1/tenants/{id}/invoices` | Create invoice |
| GET | `/api/v1/tenants/{id}/invoices` | List invoices (filters: `status`, `vendor_id`, `date_from`, `date_to`, `amount_min`, `amount_max`) |
| DELETE | `/api/v1/tenants/{id}/invoices/{invoice_id}` | Delete invoice |
| POST | `/api/v1/tenants/{id}/bank-transactions/import` | Bulk import (Header: `Idempotency-Key`) |
| POST | `/api/v1/tenants/{id}/reconcile` | Run reconciliation |
| POST | `/api/v1/tenants/{id}/matches/{match_id}/confirm` | Confirm a match |
| GET | `/api/v1/tenants/{id}/reconcile/explain` | AI explanation |

### GraphQL Operations

**Queries:**
- `tenants` - List all tenants
- `invoices(tenantId, status, amountMin, amountMax, limit, offset)` - Paginated invoices with filters
- `bankTransactions(tenantId, amountMin, amountMax, limit, offset)` - Paginated transactions
- `matchCandidates(tenantId, status)` - List match candidates
- `explainReconciliation(tenantId, invoiceId, transactionId)` - AI explanation

**Mutations:**
- `createTenant(input)` - Create tenant
- `createInvoice(tenantId, input)` - Create invoice
- `deleteInvoice(tenantId, invoiceId)` - Delete invoice
- `importBankTransactions(tenantId, input, idempotencyKey)` - Bulk import with idempotency
- `reconcile(tenantId)` - Run reconciliation
- `confirmMatch(tenantId, matchId)` - Confirm match

## Data Model

```
Tenant (1) ─────< Invoice (N)
   │                 │
   │                 └────< MatchCandidate (N)
   │                              │
   └─────< BankTransaction (N) ───┘
   │
   └─────< Vendor (N) ─────< Invoice (optional FK)
```

All entities include `created_at` timestamps. Invoice supports optional `invoice_number`, `vendor_id`, and `invoice_date`.

## Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `AI_API_URL` | AI service endpoint | `https://text.pollinations.ai/` |
| `DATABASE_URL` | SQLite connection string | `sqlite+aiosqlite:///./test.db` |