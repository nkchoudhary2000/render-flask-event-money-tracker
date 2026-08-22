# Event Money Tracker 🪙

A high-performance, full-stack Event Expense Tracking, Gift / Shagun Logging, and Cash Flow Management Application built with **Flask**, **PostgreSQL / SQLite**, **Flasgger Swagger UI**, **Google OAuth 2.0**, **Google Drive API v3**, **Flask-Login**, **Flask-CORS**, and an **asynchronous zero-reload Single Page Application (SPA) frontend** with **0ms instant tab switching**.

---

## 🌟 Key Features

1. **Dual Authentication & Account Merging**:
   - Local Email/Password authentication.
   - 1-Click Google OAuth 2.0 login.
   - Seamless account merging: If a user signs in via Google with an existing local email (or vice-versa), their credentials, tokens, and data are unified automatically.
   - **Automatic First-User Admin**: The very first user registered in the system is automatically elevated to `Admin` role.

2. **Event & Financial Management**:
   - Create and organize multiple events (e.g. *"Brother's Wedding"*, *"Ganpati Pooja 2026"*, *"Anniversary Dinner"*).
   - Dynamic custom categories per event with custom icons, color badges, and budget limits (e.g. *Catering*, *Decorations*, *Gifts Received*, *Venue*, *Photography*).
   - Dual-directional cash flows:
     - **Incoming Cash / Shagun / Gifts**: Record contributors (family/guests), amounts, payment mode (Cash, UPI, Cheque, Bank Transfer).
     - **Outgoing Expenses**: Record payees/vendors, invoice numbers, amounts, itemized notes.
   - Real-time aggregated financial analytics: Net cash balance, total income vs expenses, budget utilization, category percentage breakdowns, and top contributors/payees leaderboards.

3. **Google Drive Integration (Per-User)**:
   - Authenticate with Google Drive via OAuth 2.0.
   - Auto-creates or links a designated Drive folder (e.g. `EventMoneyTracker_Receipts`).
   - Upload receipt/bill images & PDFs directly to Google Drive asynchronously, saving Drive file IDs and shareable view links on transaction records.
   - 1-Click user data backup directly to Google Drive.

4. **Data Backup & Admin Global Backup/Restore**:
   - **User Level**: Instant JSON and CSV export downloads, or direct upload to Google Drive.
   - **Admin Level**: Comprehensive Global Database Backup (encrypted/checksummed JSON) and Transaction-safe Global Database Restore with automatic rollback on error.

5. **0ms Lag SPA Frontend**:
   - Zero full-page reloads for creating events, adding categories, recording expenses, uploading receipts, and syncing cloud backups.
   - Instant client-side tab switching across *Overview*, *Transactions*, *Categories*, *Google Drive Cloud*, and *Admin Portal*.
   - Interactive financial charts powered by Chart.js.

6. **Interactive Swagger API Documentation**:
   - Complete OpenAPI/Swagger 3.0 UI rendered at `/apidocs/` with every endpoint decorated and documented.

7. **Heavy Debug Logging**:
   - Aggressive debug logging using Python's `logging` module tracing function entries, arguments, execution duration, database transactions, external API interactions (Google Auth & Drive), and error tracebacks.

---

## 🏗️ Architecture & Project Structure

```
render-flask-event-money-tracker/
├── app.py                     # Application factory & CLI runner
├── wsgi.py                    # Production WSGI entry point (Gunicorn)
├── config.py                  # Environment configurations (Dev, Prod, Test)
├── extensions.py              # Extensions: db, login_manager, cors, swagger, migrate
├── logger.py                  # Heavy debug logging setup & execution tracing
├── models.py                  # SQLAlchemy Models (User, Event, Category, Transaction, AuditLog)
├── services/                  # Modular business logic
│   ├── auth_service.py        # Local & Google OAuth auth, merging & admin elevation
│   ├── drive_service.py       # Google Drive API v3 folder, upload & backup engine
│   ├── event_service.py       # Event, category, transaction management & financial calculations
│   └── backup_service.py      # User export/backup & Admin Global Backup/Restore engine
├── routes/                    # Rigidly separated routing layers
│   ├── api_routes.py          # RESTful JSON API with Flasgger Swagger docstrings + CORS
│   ├── ui_routes.py           # Jinja2 HTML templates for the SPA frontend
│   └── auth_routes.py         # Google OAuth & Local Auth endpoints
├── templates/                 # Glassmorphic Jinja2 templates
│   ├── base.html              # Layout, toasts, modals, navigation
│   ├── login.html             # Login view (Local + Google 1-Click)
│   ├── register.html          # Registration view
│   └── dashboard.html         # 0ms Lag Tabbed SPA Dashboard
├── static/
│   ├── css/
│   │   └── style.css          # Luxury dark design system, glassmorphism, responsive
│   └── js/
│       └── app.js             # Client SPA controller (0ms tab switcher, AJAX, Chart.js)
├── requirements.txt           # Python dependencies
├── .env.example               # Environment variables template
├── Procfile                   # Gunicorn process config for Render.com
├── render.yaml                # Render.com Blueprint (Web + PostgreSQL)
└── README.md                  # Comprehensive documentation
```

---

## 🚀 Quickstart & Local Setup

### 1. Clone & Setup Virtual Environment
```bash
git clone <repository-url>
cd render-flask-event-money-tracker

# Create and activate virtual environment
python -m venv venv
# On Windows:
.\venv\Scripts\activate
# On Linux/macOS:
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

### 2. Configure Environment Variables
Copy `.env.example` to `.env`:
```bash
cp .env.example .env
```
Edit `.env` as needed:
```env
FLASK_APP=wsgi.py
FLASK_ENV=development
SECRET_KEY=replace_with_a_secure_random_key
DATABASE_URL=sqlite:///event_tracker.db
LOG_LEVEL=DEBUG

# Optional for Google OAuth / Drive (app runs in local mode without them):
GOOGLE_CLIENT_ID=your-google-client-id.apps.googleusercontent.com
GOOGLE_CLIENT_SECRET=your-google-client-secret
```

### 3. Run the Application
```bash
python app.py
```
Open your browser and navigate to:
- **Application Dashboard:** `http://localhost:5000`
- **Swagger API Documentation:** `http://localhost:5000/apidocs/`

---

## 🔑 Google OAuth 2.0 & Google Drive Setup

To enable Google Sign-In and Google Drive receipt/backup sync:
1. Visit the [Google Cloud Console](https://console.cloud.google.com/).
2. Create a new project (e.g. *Event Money Tracker*).
3. Under **APIs & Services > Library**, search for and enable **Google Drive API**.
4. Under **APIs & Services > OAuth consent screen**:
   - Choose **External**.
   - Add scopes: `openid`, `.../auth/userinfo.email`, `.../auth/userinfo.profile`, `.../auth/drive.file`.
5. Under **APIs & Services > Credentials**:
   - Create **OAuth 2.0 Client ID** (Web application).
   - Set **Authorized redirect URIs**:
     - Local: `http://localhost:5000/auth/google/callback`
     - Production: `https://<your-render-app>.onrender.com/auth/google/callback`
6. Copy the **Client ID** and **Client Secret** into your `.env` file or Render environment variables.

---

## 🌐 Deploying to Render.com

This repository includes a `render.yaml` Blueprint and `Procfile` configured for zero-friction deployment on **Render.com**.

### Method 1: Deploy with Render Blueprint (`render.yaml`)
1. Push your repository to GitHub.
2. Log in to [Render.com](https://render.com) and click **Blueprints > New Blueprint Instance**.
3. Connect your repository. Render will automatically provision:
   - A **Managed PostgreSQL Database** (`event-tracker-db`).
   - A **Python 3 Web Service** running Gunicorn with workers and SSL.
4. Set your `GOOGLE_CLIENT_ID` and `GOOGLE_CLIENT_SECRET` in the Render dashboard environment settings.

### Method 2: Manual Web Service on Render
- **Environment:** Python
- **Build Command:** `pip install -r requirements.txt`
- **Start Command:** `gunicorn wsgi:app`
- **Environment Variables:**
  - `DATABASE_URL`: Your PostgreSQL connection string (or internal Render database URL).
  - `SECRET_KEY`: A strong random string.
  - `FLASK_ENV`: `production`

---

## 📖 API Documentation & Swagger

All API endpoints are documented with OpenAPI 3.0 specs. Access the interactive UI at `/apidocs/`.

### Key Endpoints:
| Method | Endpoint | Description | Auth Required |
|---|---|---|---|
| `GET` | `/api/auth/me` | Current user profile | Yes |
| `GET` | `/api/events` | List all user events with stats | Yes |
| `POST` | `/api/events` | Create a new event | Yes |
| `GET` | `/api/events/{id}/analytics` | Full financial aggregates & breakdown | Yes |
| `GET` | `/api/events/{id}/transactions` | Query & filter transactions | Yes |
| `POST` | `/api/events/{id}/transactions` | Add expense or incoming gift (+ receipt) | Yes |
| `DELETE` | `/api/transactions/{id}` | Delete a transaction | Yes |
| `GET` | `/api/events/{id}/categories` | List categories with subtotals | Yes |
| `POST` | `/api/events/{id}/categories` | Create custom category | Yes |
| `GET` | `/api/drive/status` | Google Drive connection status | Yes |
| `POST` | `/api/drive/backup-user-data` | Upload user backup to Google Drive | Yes |
| `GET` | `/api/backup/export` | Download backup as JSON or CSV | Yes |
| `GET` | `/api/admin/backup` | Download complete database state (JSON) | Admin Only |
| `POST` | `/api/admin/restore` | Restore database state from backup | Admin Only |
| `GET` | `/api/admin/stats` | System counts & audit trail | Admin Only |

---

## 🛡️ Admin Privileges & Safety

- The **first user** to register in the database is automatically granted `is_admin = True`.
- The Admin Portal provides:
  - System-wide transaction metrics and user statistics.
  - **Global Database Backup:** Generates an integrity-hashed SHA-256 JSON dump of all tables.
  - **Global Database Restore:** Uploads a JSON backup and restores all tables inside an atomic database transaction. If any data is malformed, changes are rolled back with zero data corruption.
  - **Security Audit Logs:** Tracks logins, password additions, backups, and restores with IP addresses and timestamps.
