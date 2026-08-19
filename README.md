# Safi Ullah — AI/ML Portfolio & Production CMS

A secure, data-driven, production-grade personal portfolio and Content Management System (CMS) built with Flask, SQLAlchemy, Jinja2, Vanilla CSS, and modern web standards.

---

## Key Features

- **Production-Quality CMS**: Full-featured admin dashboard (`/admin`) for managing projects, technical skills, education, work experience, certifications, contact inquiries, and profile settings without touching code.
- **Dynamic ML Project Pages**: Rich project detail pages (`/projects/<slug>`) documenting problem statements, datasets, model architectures, preprocessing pipelines, metrics (accuracy, precision, recall, F1, ROC-AUC), limitations, and future work.
- **Security Hardened**:
  - CSRF protection on all mutating forms and AJAX requests (`Flask-WTF`).
  - Rate limiting on public and authentication endpoints (`Flask-Limiter`).
  - Strict Content Security Policy (CSP), X-Frame-Options, X-Content-Type-Options, Referrer-Policy, and Permissions-Policy headers.
  - Secure image upload validation (magic bytes verification via Pillow, filename randomization, size enforcement).
  - Secure password hashing with Werkzeug PBKDF2-SHA256.
  - Zero hardcoded secrets; environment variable configuration via `.env`.
  - Email OTP (one-time password) verification for password resets and credential changes.
  - Database-backed contact form (eliminated insecure public JSON storage).
  - Admin registration allow-list (`ALLOWED_ADMIN_EMAILS`) to prevent unauthorized accounts.
- **CV / Resume Download**: One-click CV download (`Download My CV`) from the hero section serving a formatted PDF at `static/cv/safi_ullah_cv.pdf`.
- **Accessibility & SEO**: Semantic HTML5 landmarks, ARIA attributes, structured metadata, OpenGraph cards, auto-generated `sitemap.xml`, and `robots.txt`.
- **Dockerized**: Multi-stage production `Dockerfile` with non-root user, healthcheck, and `docker-compose.yml` with persistent volume management.

---

## Technology Stack

- **Backend**: Python 3.12+ / Flask 3.1+
- **Database & ORM**: SQLAlchemy / Flask-SQLAlchemy (SQLite default, PostgreSQL ready)
- **Forms & Security**: Flask-WTF, Flask-Limiter, Werkzeug, Pillow 12+
- **Frontend**: Vanilla CSS, Modern JavaScript (ES6+), Canvas Particles, Font Awesome 6
- **Testing**: pytest 9+ (23 unit and integration tests)
- **Deployment**: Gunicorn WSGI, Docker, Docker Compose

---

## Project Structure

```
SafiUllah_Portfolio_Website/
├── app.py                      # Flask application factory, CLI commands, error handlers
├── config.py                   # Multi-environment configurations (Dev, Prod, Test)
├── extensions.py               # Extension initializers (db, csrf, mail, limiter)
├── models.py                   # SQLAlchemy database models (8 entities)
├── requirements.txt            # Pinned dependencies
├── Dockerfile                  # Multi-stage production container
├── docker-compose.yml          # Container orchestration & volume mapping
├── .env.example                # Environment variable blueprint (sanitized, no real secrets)
├── blueprints/
│   ├── public/                 # Public portfolio routes & SEO endpoints
│   │   ├── __init__.py
│   │   └── routes.py
│   └── admin/                  # Admin CMS routes & authentication
│       ├── __init__.py
│       └── routes.py
├── utils/
│   ├── __init__.py
│   └── security.py             # Image validation & security headers middleware
├── templates/
│   ├── base.html               # Base layout with SEO & OpenGraph
│   ├── index.html              # Main portfolio homepage
│   ├── project_detail.html     # Deep-dive ML project case study
│   ├── errors/                 # Error templates (400, 403, 404, 429, 500)
│   └── admin/                  # CMS admin panel templates
│       ├── base_admin.html
│       ├── login.html
│       ├── dashboard.html
│       ├── projects_list.html
│       ├── project_form.html
│       ├── skills.html
│       ├── education.html
│       ├── experience.html
│       ├── certifications.html
│       ├── messages.html
│       └── settings.html
├── static/
│   ├── css/
│   │   ├── style.css           # Public stylesheet
│   │   └── admin.css           # Admin CMS stylesheet
│   ├── js/
│   │   ├── script.js           # Public interactions, CSRF contact form, particles
│   │   └── admin.js            # Admin interactions & modals
│   ├── cv/
│   │   └── safi_ullah_cv.pdf   # Downloadable CV
│   └── uploads/                # User-uploaded images (projects, certs, profile)
├── tests/
│   └── test_app.py             # Automated test suite (pytest)
└── logs/
    └── portfolio.log           # Application logs
```

---

## Getting Started

### 1. Setup Environment

```bash
# Create virtual environment
python -m venv venv

# Activate virtual environment
# On Windows:
.\venv\Scripts\activate
# On Linux/macOS:
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

### 2. Configure Environment Variables

Copy `.env.example` to `.env` and fill in your settings:

```bash
cp .env.example .env
```

Key environment variables:

| Variable | Required | Description |
|---|---|---|
| `SECRET_KEY` | **Yes** | Random 64+ hex string. Generate: `python -c "import secrets; print(secrets.token_hex(32))"` |
| `FLASK_ENV` | Yes | `development` or `production` |
| `DATABASE_URL` | No | SQLite (default) or PostgreSQL URI |
| `ALLOWED_ADMIN_EMAILS` | Yes | Comma-separated list of emails allowed to register as admin |
| `CONTACT_RECIPIENT_EMAIL` | No | Email to receive contact form notifications |
| `MAIL_USERNAME` | No | SMTP email address for OTP emails |
| `MAIL_PASSWORD` | No | SMTP app password (e.g. Gmail App Password) |

> **Security**: Never commit `.env` to version control. The `.gitignore` excludes it.

### 3. Initialize & Seed Database

```bash
# Create database tables and seed initial portfolio content
python -m flask init-db
```

### 4. Create Admin User

There are two ways to create an admin:

**Option A — CLI (Recommended for initial setup):**
```bash
python -m flask create-admin <username> <email>
# You will be prompted securely for the password.
```

**Option B — Web registration:**
1. Add your email to `ALLOWED_ADMIN_EMAILS` in `.env`
2. Visit `/admin/register`
3. Complete OTP email verification

### 5. Run the Application

**Development:**
```bash
flask run
# or
python app.py
```

**Production (Gunicorn):**
```bash
gunicorn --bind 0.0.0.0:5000 --workers 3 app:create_app()
```

Visit:
- Public Portfolio: [http://localhost:5000](http://localhost:5000)
- Admin Panel: [http://localhost:5000/admin](http://localhost:5000/admin)

---

## Backup Procedure

### SQLite Database Backup
```bash
# Copy the database file (safe because SQLite supports hot copies for read)
cp instance/portfolio.db instance/portfolio.db.backup.$(date +%Y%m%d)
```

### Uploaded Media Backup
```bash
# Archive all uploaded images
tar -czf uploads_backup_$(date +%Y%m%d).tar.gz static/uploads/
```

### Docker Volume Backup
```bash
# Backup the named volumes
docker run --rm -v portfolio_data:/data -v $(pwd):/backup alpine tar czf /backup/db_backup.tar.gz /data
docker run --rm -v portfolio_uploads:/data -v $(pwd):/backup alpine tar czf /backup/uploads_backup.tar.gz /data
```

---

## Testing & Security Auditing

### Automated Unit & Integration Tests (pytest)

```bash
python -m pytest tests/ -v
```

Tests cover:
- Public endpoints & status codes (200, 404)
- Dynamic ML project detail pages (`/projects/<slug>`)
- Project draft vs published visibility enforcement
- Project deletion and lifecycle
- Contact form validation and CSRF protection
- robots.txt and sitemap.xml with `<lastmod>`
- Security response headers (CSP, Frame protection)
- Unauthenticated access prevention and redirection across all admin routes
- Admin login, logout, and session lifecycle
- One-time password (OTP) credential changes and password resets
- XSS prevention and sanitization
- Image upload validation and non-image payload rejection

### Security Scans

```bash
# Python security linter
python -m bandit -r . --exclude ./.venv,./tests,./logs,./.pytest_cache

# Dependency vulnerability scanner
python -m pip_audit -r requirements.txt
```

---

## Docker Deployment

### Build and Start

```bash
docker compose build --no-cache
docker compose up -d
```

### Initialize Database (First Run)

```bash
docker compose exec web flask init-db
docker compose exec web flask create-admin <username> <email>
```

### Docker Restart Test

Data persists across container restarts because volumes are used:
- `portfolio_data` → SQLite database (`/app/instance/`)
- `portfolio_uploads` → Uploaded images (`/app/static/uploads/`)
- `portfolio_logs` → Application logs (`/app/logs/`)

```bash
docker compose restart
# All data remains intact
```

The application runs using production Gunicorn WSGI workers (3 workers) behind a non-root user with persistent storage.

### Production Environment Variables for Docker

Set these in your `.env` file or via `docker compose` environment configuration:

```env
FLASK_ENV=production
SECRET_KEY=<generate-a-secure-random-64-char-hex-key>
CONTACT_RECIPIENT_EMAIL=your@email.com
MAIL_USERNAME=your@email.com
MAIL_PASSWORD=your-smtp-app-password
ALLOWED_ADMIN_EMAILS=your@email.com
```

---

## Admin CMS Workflow

### Initial Setup
```bash
flask init-db
flask create-admin <username> <email>
```

### Daily CMS Usage

1. **Login**: Navigate to `/admin/login`
2. **Projects**: Create/edit/delete/publish ML projects with images, metrics, and tech stacks
3. **Skills**: Manage skills with proficiency bars and technology tags
4. **Education & Experience**: Timeline management
5. **Certifications**: Add credentials with images and links
6. **Messages**: Review and manage contact form submissions
7. **Settings**: Update profile, bio, hero text, social links, and SEO metadata
8. **Logout**: Session expires automatically after 8 hours or on manual logout

### Security: Password & Username Changes

All credential changes require:
1. Confirming your **current password**
2. Entering a **6-digit OTP** sent to your registered email

Navigate to **Settings → Security: Change Username & Password**.

---

## Troubleshooting

**"Database not found" on startup:**
```bash
flask init-db
```

**OTP not received:**
- Check SMTP configuration in `.env`
- In development mode, OTP is shown in flash messages

**"Invalid image file" on upload:**
- Only PNG, JPG, WebP formats supported
- Maximum 5 MB file size
- File must be a valid image (verified by Pillow)

**Admin login not working:**
```bash
flask reset-password <username>
```

**Docker: Port already in use:**
```bash
docker compose down
docker compose up -d
```
