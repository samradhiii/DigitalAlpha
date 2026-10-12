# Assessment Notes

## App name

**Fund Reconciliation** (Capital Call Bank Reconciliation)

## What the app does

A fund manager sends "capital calls" to investors, asking them to pay in money. Investors then pay by bank transfer.
This app helps work out which payment belongs to which capital call.

1. You upload a bank statement (CSV file).
2. The app checks every row, skips bad rows and duplicates, and suggests a match for each payment.
3. A reviewer approves, rejects or ignores each payment.
4. When a payment is approved, the capital call's paid amount, remaining amount and status are updated.

**Built with:** React 18 (Vite) for the frontend, Django 5.2 + Django REST Framework for the backend, and
PostgreSQL 16 for the database.

```
backend/      Django project (config/) and the "reconciliation" app
frontend/     React app
sample_data/  sample_bank_statement.csv to try the app with
docker-compose.yml   starts PostgreSQL for local use
```

---

## 1. Setup instructions

### What you need first

- Python 3.10 or newer
- Node.js 18 or newer
- PostgreSQL (the easiest way is Docker)

### Step 1: Start the database

From the project folder:

```bash
docker compose up -d
```

This starts PostgreSQL on `localhost:5433`. The database name, user and password are all `fund_recon`.
Port 5433 is used so it does not clash with another PostgreSQL that may already be using 5432.

### Step 2: Start the backend

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate          # on Windows
# source .venv/bin/activate     # on macOS / Linux
pip install -r requirements.txt
python manage.py migrate        # creates the tables
python manage.py seed_demo      # adds demo organizations, users, investors and capital calls
python manage.py runserver      # backend runs at http://127.0.0.1:8000
```

Want to start the demo fresh? Run `python manage.py seed_demo --reset`. It deletes all uploads, transactions
and payments for the demo organizations and puts the balances back to the start.

### Step 3: Start the frontend

Open a second terminal:

```bash
cd frontend
npm install
npm run dev                     # frontend runs at http://localhost:5173
```

The frontend sends every `/api` request to the backend on port 8000, so both must be running.

### Step 4: Log in

| Organization | Username | Password |
|---|---|---|
| Northwind Ventures | `northwind_admin` | `demo12345` |
| Bluebird Capital | `bluebird_admin` | `demo12345` |

Log in as `northwind_admin` and upload `sample_data/sample_bank_statement.csv` to see the app in action.

---

## 2. Environment configuration

The app reads these settings from environment variables. If a variable is not set, the default is used, and the
defaults already work with the Docker database above.

| Variable | Default | What it is for |
|---|---|---|
| `POSTGRES_DB` | `fund_recon` | Database name |
| `POSTGRES_USER` | `fund_recon` | Database user |
| `POSTGRES_PASSWORD` | `fund_recon` | Database password |
| `POSTGRES_HOST` | `localhost` | Database server address |
| `POSTGRES_PORT` | `5433` | Database port |
| `DJANGO_SECRET_KEY` | a development-only key | Secret key for Django. **Always set your own outside local development.** |
| `DJANGO_DEBUG` | `true` | Set to `false` in production |
| `DJANGO_ALLOWED_HOSTS` | `localhost,127.0.0.1` | Comma-separated list of domain names the backend will answer to |

The database user needs permission to create databases (`CREATEDB`), because the tests create their own
temporary test database.

---

## 3. How to run the tests

```bash
cd backend
python manage.py test reconciliation
```

There are **57 tests**, and they all pass. They live in `backend/reconciliation/tests/`:

| File | What it checks |
|---|---|
| `test_csv_parser.py` | Reading the CSV: required columns, file encoding, empty files, bad dates, bad amounts, bad types, wrong number of columns, blank lines, amounts like "25,000.00", debit signs |
| `test_matching.py` | Finding capital call references (`CC-1001`, `cc1001`, `CC 1001`), matching investor names, scoring, part payments, over-payments, conflicting reference and name, payments made before the call date, investors with several open calls, calls already fully paid, references from another organization |
| `test_import.py` | The whole sample file line by line, duplicates in the same file and across uploads, file-level errors that save nothing, the upload endpoint |
| `test_approvals.py` | Approve, reject and ignore; paid / remaining / status updates; part payments; approving twice; paying more than is owed; choosing a call by hand; database rules |
| `test_security.py` | Login is required; users without an organization are blocked; one organization can never see or change another organization's data |

---

## 4. API endpoints

Every endpoint except login needs this header:

```
Authorization: Token <your token>
```

You get the token from the login endpoint. Each user only ever sees their own organization's data. If you ask for
something that belongs to another organization, you get **404 Not Found**.

| Method | Path | What it does |
|---|---|---|
| POST | `/api/auth/login/` | Send `{username, password}`. Returns `{token, username, organization}` |
| POST | `/api/auth/logout/` | Logs out (the token stops working) |
| GET | `/api/me/` | The logged-in user and their organization |
| GET | `/api/investors/` | All investors, with total called, total paid, amount still owed and payment status |
| GET | `/api/capital-calls/?status=` | All capital calls with paid and remaining amounts. Can be filtered by status |
| GET | `/api/imports/` | List of past uploads with summary counts |
| POST | `/api/imports/` | Upload a CSV file (form field `file`, max 5 MB). Returns the summary, rejected rows and imported transactions |
| GET | `/api/imports/{id}/` | One upload with its rejected rows and transactions |
| GET | `/api/transactions/?status=&import=` | Bank transactions. Can be filtered by status and by upload |
| GET | `/api/transactions/{id}/` | One transaction |
| POST | `/api/transactions/{id}/approve/` | Approve a payment. Optional `capital_call_id` (to choose a different call) and `note` |
| POST | `/api/transactions/{id}/reject/` | Reject the suggested match. Optional `note` |
| POST | `/api/transactions/{id}/ignore/` | Mark it as not a capital call payment (for example, a bank fee). Optional `note` |

Error codes to know:
- **400**: the uploaded file has a problem (for example, a missing column), and nothing was saved.
- **409**: the action breaks a business rule, for example approving something twice or paying more than is owed.
  The response has a `detail` message explaining why.

---

## 5. Database models

How the tables connect:

```
Organization ─┬─ Membership        (links each user to one organization)
              ├─ Investor ── CapitalCall      (one call notice per investor, e.g. CC-1001)
              ├─ StatementImport ─┬─ ImportRowIssue    (rows that were invalid or duplicates)
              │                   └─ BankTransaction   (rows that were imported, with the match suggestion)
              └─ Payment           (an approved bank transaction applied to a capital call)
```

| Model | What it stores | Rules the database enforces |
|---|---|---|
| **Organization** | A fund manager company (name, slug) | Name and slug are unique |
| **Membership** | Which organization a user belongs to | A user belongs to exactly one organization |
| **Investor** | An investor in the fund (name, email) | Investor names are unique within an organization |
| **CapitalCall** | A request for money sent to one investor: reference, call date, due date, amount called, amount paid so far, status (`PENDING`, `PARTIALLY_FUNDED`, `FUNDED`) | Reference is unique within an organization. Amount called must be above 0. Amount paid can never be below 0 or above the amount called |
| **StatementImport** | One uploaded CSV file: file name, who uploaded it, when, and summary counts | — |
| **ImportRowIssue** | A row that was not imported: its line number, why (`INVALID` or `DUPLICATE`), the error messages and the original row | — |
| **BankTransaction** | One imported bank row: date, description, amount, credit/debit, bank reference, status, suggested investor and call, confidence score, reasons, and who reviewed it | The same bank transaction can never be imported twice for one organization |
| **Payment** | An approved payment: which transaction paid which capital call, the amount, who approved it and when | One transaction can create at most one payment. Amount must be above 0 |

The investor totals (called, paid, still owed) are not stored separately. They are added up from the investor's
capital calls every time, so they can never get out of sync.

---

## 6. How the matching works (short version)

- **Only money coming in (credits) is matched.** Money going out (debits, like bank fees) is ignored automatically.
- Each payment gets points:
  - **+40** if the description contains a capital call reference such as `CC-1001`
  - **+40** if the description contains the investor's name (case, punctuation and endings like "LLC" or "Inc" do not matter)
  - **+20** if the amount exactly matches what is still owed on the call
- **60 points or more**, with no warning signs, gives a **Suggested** match. Anything else goes to **Needs review**,
  and the best guess is still shown so the reviewer can approve it with one click.
- These warning signs always send a payment to review: the payment is bigger than what is owed, the reference is
  unknown, the reference and the name point to different investors, the name matches more than one investor, the
  investor has several open calls and the amount doesn't make clear which one, or the payment is dated before the
  call was sent.
- **Duplicates** are found using the bank reference. If there is no bank reference, the app uses date + amount +
  description instead.
- **Approvals are safe.** An approval happens in one database transaction that locks the rows, so the same payment
  can't be approved twice and a call can't be paid more than it is owed.

---

## 7. Assumptions

- A **capital call** is a notice to *one* investor with its own reference (for example, `CC-1001` is Haller Capital
  LLC's call). This is how references appear in the sample bank statement.
- All money is in **one currency (USD)**. An "exact amount match" must be correct to the cent.
- One payment goes to **one capital call only**, and only up to what is still owed. If an investor pays too much,
  the app does not split it automatically. A person decides what to do.
- **Approvals are final.** There is no "undo approval" in this version.
- The bank `reference` column is treated as the unique ID of a bank transaction. If it is empty, date + amount +
  description is used to spot duplicates.
- Each organization has its own separate investors. Two organizations can each have an investor with the same name
  (for example, "Meridian Partners"), and they are treated as different investors.
- The demo data includes one capital call (`CC-1005`) that is already fully paid, to show that fully paid calls are
  never suggested as matches.
- Row numbers in error messages are the **line numbers in the CSV file** (the header is line 1), so you can find the
  row easily in Excel.
- **No AI or "fuzzy matching" libraries** are used. Every match follows clear rules that can be explained.
