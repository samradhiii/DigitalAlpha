# Capital Call Bank Reconciliation

A full-stack app that helps a fund manager work out which investor has paid against which capital call. Upload a
bank statement CSV, and the app validates it, drops duplicates, suggests investor/capital-call matches and lets a
reviewer approve, reject or ignore each payment. Approved payments update the capital call's funded amount, remaining
balance and payment status.

**Stack:** React 18 (Vite) · Django 5.2 · Django REST Framework · PostgreSQL 16

```
backend/    Django project (config/) and the `reconciliation` app
frontend/   React single-page app
sample_data/sample_bank_statement.csv
docker-compose.yml   PostgreSQL for local development
```

---

## 1. Installation & setup

Prerequisites: Python 3.10+, Node 18+, and PostgreSQL (Docker is the easiest way to get it).

### Database

```bash
docker compose up -d          # PostgreSQL 16 on localhost:5433 (db/user/password: fund_recon)
```

Port 5433 is used to avoid clashing with any PostgreSQL already on 5432. To use your own server instead, create a
database and set the environment variables below.

| Variable | Default |
|---|---|
| `POSTGRES_DB` | `fund_recon` |
| `POSTGRES_USER` | `fund_recon` |
| `POSTGRES_PASSWORD` | `fund_recon` |
| `POSTGRES_HOST` | `localhost` |
| `POSTGRES_PORT` | `5433` |
| `DJANGO_SECRET_KEY` | dev-only key, **set this outside development** |
| `DJANGO_DEBUG` | `true` |

The database user needs `CREATEDB` permission so the test runner can create its test database.

### Backend

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate            # Windows  (macOS/Linux: source .venv/bin/activate)
pip install -r requirements.txt
python manage.py migrate
python manage.py seed_demo        # demo organizations, users, investors, capital calls
python manage.py runserver        # http://127.0.0.1:8000
```

`python manage.py seed_demo --reset` wipes all imports, transactions and payments for the demo organizations and
restores the original balances. It's handy for re-running the demo.

### Frontend

```bash
cd frontend
npm install
npm run dev                       # http://localhost:5173 (proxies /api to :8000)
```

### Demo logins

| Organization | Username | Password |
|---|---|---|
| Northwind Ventures | `northwind_admin` | `demo12345` |
| Bluebird Capital | `bluebird_admin` | `demo12345` |

Sign in as `northwind_admin` and upload `sample_data/sample_bank_statement.csv`.

---

## 2. Running the tests

```bash
cd backend
python manage.py test reconciliation
```

57 tests in `backend/reconciliation/tests/`:

| File | Covers |
|---|---|
| `test_csv_parser.py` | Required columns, encoding, empty files, date/amount/type validation, column-count errors, blank lines, comma-formatted amounts, debit sign handling, dedupe keys |
| `test_matching.py` | Reference extraction (`CC-1001`, `cc1001`, `CC 1001`), name normalisation, scoring, partial payments, over-payments, reference/name conflicts, payments dated before the call, multiple open calls, already-funded calls, references from another organization, in-batch reservations |
| `test_import.py` | Full sample-file outcome line by line, duplicates within a file and across imports, duplicates without a bank reference, file-level errors writing nothing, the upload endpoint |
| `test_approvals.py` | Approve/reject/ignore, funded/remaining/status updates, partial funding, double approval, over-funding, manual call selection, state transitions, DB constraints |
| `test_security.py` | Authentication, users without an organization, list/detail isolation, cross-org approve/reject/ignore, applying a payment to another org's capital call, per-org duplicate detection |

---

## 3. Database models

```
Organization ─┬─ Membership (1 user ↔ 1 organization)
              ├─ Investor ── CapitalCall (one call notice per investor, e.g. CC-1001)
              ├─ StatementImport ─┬─ ImportRowIssue (invalid / duplicate rows that were not imported)
              │                   └─ BankTransaction (imported rows + match suggestion + review state)
              └─ Payment (approved BankTransaction → CapitalCall)
```

| Model | Key fields | Integrity rules |
|---|---|---|
| `Organization` | name, slug | unique name/slug |
| `Membership` | user (one-to-one), organization | a user belongs to exactly one organization |
| `Investor` | organization, name, email | unique (organization, name) |
| `CapitalCall` | organization, investor, reference, call_date, due_date, amount_called, amount_funded, status | unique (organization, reference); `amount_called > 0`; `0 ≤ amount_funded ≤ amount_called` (DB check constraints). `remaining_amount` = called − funded. Status: `PENDING` / `PARTIALLY_FUNDED` / `FUNDED` |
| `StatementImport` | organization, uploaded_by, file_name, summary counts | — |
| `ImportRowIssue` | import, row_number (CSV line), issue_type (`INVALID`/`DUPLICATE`), messages, raw_data | — |
| `BankTransaction` | organization, import, row_number, date, description, amount, type, bank_reference, dedupe_key, status, suggested investor/call, confidence, match_reasons, review_reasons, reviewed_by/at, review_note | unique (organization, dedupe_key), so the same bank transaction can never be imported twice |
| `Payment` | organization, capital_call, bank_transaction (one-to-one), amount, approved_by/at | one-to-one on the transaction, so a transaction can fund at most once; `amount > 0` |

Investor-level totals (called, funded, remaining, payment status) are aggregated from the investor's capital calls in
the `/api/investors/` endpoint, so they can never drift from the call balances.

---

## 4. API endpoints

All endpoints except login require `Authorization: Token <token>`. Every query is filtered to the caller's
organization, so objects belonging to another organization return **404**.

| Method | Path | Description |
|---|---|---|
| POST | `/api/auth/login/` | `{username, password}` → `{token, username, organization}` |
| POST | `/api/auth/logout/` | Revokes the token |
| GET | `/api/me/` | Current user and organization |
| GET | `/api/investors/` | Investors with total called / funded / remaining and payment status |
| GET | `/api/capital-calls/?status=` | Capital calls with funded and remaining amounts |
| GET | `/api/imports/` | Import history with summary counts |
| POST | `/api/imports/` | Multipart `file` (CSV, ≤ 5 MB). Returns the import summary, rejected rows and imported transactions (201). File-level problems → 400 |
| GET | `/api/imports/{id}/` | One import with its issues and transactions |
| GET | `/api/transactions/?status=&import=` | Transactions, filterable by status and import |
| GET | `/api/transactions/{id}/` | One transaction |
| POST | `/api/transactions/{id}/approve/` | `{capital_call_id?, note?}`. Applies the payment to the suggested call, or to `capital_call_id` if given |
| POST | `/api/transactions/{id}/reject/` | `{note?}`. Rejects the suggested match |
| POST | `/api/transactions/{id}/ignore/` | `{note?}`. Marks the transaction as not a capital-call payment |

A business-rule violation (already approved, over-funding, no call chosen, invalid state) returns **409** with a
`detail` message.

---

## 5. How it works

### CSV validation (`reconciliation/csv_parser.py`)

* **File level** (the whole upload is rejected and nothing is written): not UTF-8, empty, no data rows, missing any of
  `date, description, amount, type, reference` (header match ignores case and whitespace, and tolerates a BOM),
  more than 10,000 rows, or malformed CSV.
* **Row level** (the row is reported and skipped, and the rest of the file still imports):
  * `date` must be `YYYY-MM-DD` and a real calendar date (`2026-04-31` is rejected)
  * `amount` must be numeric with at most 2 decimals and must not be zero. Thousands separators and `$` are accepted
    (`"25,000.00"`).
  * `type` must be `credit` or `debit` (any case)
  * credits must be positive. Debits are stored as negative whether the bank signs them or not.
  * description is required. Surrounding and repeated whitespace is collapsed.
  * a row with more or fewer columns than the header is invalid
* Row numbers are CSV **line numbers**, so the header is line 1. This makes it easy to find a row in Excel.

### Duplicate detection

Each row gets a `dedupe_key`: the bank reference (case-insensitive) when present, otherwise
`date | amount | normalised description`. A row is a duplicate if the key appears earlier in the same file or was
imported before for the **same organization**. A unique DB constraint on `(organization, dedupe_key)` backs this up,
and imports are serialised per organization with a row lock, so concurrent uploads can't race past the check.

### Matching (`reconciliation/matching.py`)

The matching is deterministic and rule-based. Only credits are matched. Debits (e.g. bank fees) are auto-ignored.

| Signal | Points |
|---|---|
| Capital call reference in description (`CC-1001`, `cc1001`, `CC 1001`), belonging to this organization | +40 |
| Investor name in description (normalised: case, punctuation and whitespace; trailing LLC/INC/LP/LTD… ignored) | +40 |
| Amount exactly equals the call's available balance | +20 |

When there is no reference, the call is chosen from the named investor's open calls. If there are several, the call
whose balance exactly equals the amount wins. Otherwise the payment goes to review.

A payment is **Suggested** when the score is ≥ 60 and no review flag was raised. Otherwise it goes to **Needs review**,
keeping the best candidate so the reviewer can approve with one click. These flags always force review:

* the amount is larger than the call's available balance (*too large*)
* the reference is not found in this organization
* the reference and the investor name point to different investors
* the description matches several investors equally
* the investor has several open calls and the amount doesn't single one out
* the payment is dated before the capital call was issued
* low confidence (e.g. a name-only partial payment)

"Available balance" = remaining balance − amounts already earmarked by other unreviewed suggestions (from this file or
earlier imports). This stops two payments being suggested against the same outstanding amount.

### Review and approval (`reconciliation/services.py`)

| From status | Approve | Reject | Ignore |
|---|---|---|---|
| Suggested / Needs review | ✓ | ✓ | ✓ |
| Rejected | ✓ (must choose a call explicitly) | — | ✓ |
| Approved / Ignored | — | — | — |

Approval runs in one database transaction. It locks the bank transaction and capital call rows
(`SELECT … FOR UPDATE`) and re-checks the status, so a second approval fails. It also refuses any amount above the
call's remaining balance. It then creates a `Payment`, increases `amount_funded` and recalculates the call status.
DB constraints (one `Payment` per transaction, `amount_funded ≤ amount_called`) are a second line of defence against
duplicate or over-funding.

### Organization security

* Token authentication. Each user belongs to exactly one organization through `Membership`. Users without one get 403.
* Every view filters its queryset by the caller's organization. An approve request with a `capital_call_id` is resolved
  inside the caller's organization too, so a Northwind user can't fund a Bluebird call even if they know its ID.
* Matching only sees the uploading organization's investors and calls. Duplicate detection is also per organization.

---

## 6. Sample file walkthrough (Northwind Ventures)

| Line | Row | Outcome |
|---|---|---|
| 2 | Rahul Shah Trust, CC-1002, 25,000 | Suggested, 100% |
| 3 | Haller Capital LLC, CC-1001, 20,000 | Suggested, 100% |
| 4 | Bank fee, debit | Ignored automatically |
| 5 | Patel Family Trust, no reference, 12,500 | Needs review: name-only partial payment (candidate CC-1003) |
| 6 | `"  wire incoming meridian partners  "`, 15,000 | Suggested, 60%: name + exact amount |
| 7 | Unknown incoming wire | Needs review: no reference or known name |
| 8 | Oakridge Holdings, no reference, 15,000 | Suggested CC-1006 (CC-1005 is already funded) |
| 9 | Haller `cc1001`, 7,500 | Needs review: exceeds available balance |
| 10 | Patel CC-1003, 13,000 | Needs review: 12,500 + 13,000 > 25,000 |
| 11 | Repeat of line 2 | Duplicate, not imported |
| 12 | Cedar Grove Fund, CC-2001 | Needs review: CC-2001 belongs to Bluebird and isn't visible to Northwind |
| 13 | Date 2026-04-31 | Invalid, not imported |
| 14 | Credit of −15,000 | Invalid, not imported |
| 15 | Oakridge CC-1006, dated 2026-03-20 | Needs review: before the call date and exceeds available balance |

Summary: 14 rows → 11 imported (4 suggested, 6 need review, 1 ignored), 1 duplicate, 2 invalid.

---

## 7. Assumptions

* A **capital call** here is a per-investor call notice with its own reference (`CC-1001` → Haller Capital LLC), which
  is how references appear in the sample statement. A fund-level call is the set of notices that share a call date.
* Amounts are in a single currency (USD), and an amount match must be exact to the cent.
* A payment can only be applied to a single capital call, and only up to its remaining balance. Over-payments are left
  for manual handling (e.g. part-approve after the investor confirms, or ignore and refund) rather than auto-split.
* Approvals are final in this version. There is no un-approve or reversal flow.
* Seed data includes CC-1005 as an already-funded historical call, to show that fully funded calls aren't match
  candidates.
* The bank `reference` column is the transaction's unique ID for duplicate detection. It may be blank, in which case
  date + amount + description is used.
* Bluebird Capital also has an investor named "Meridian Partners". Investors are per organization, so this is a
  separate investor from Northwind's.
* No AI or fuzzy-matching libraries are used. All matching is explicit, explainable rules.
