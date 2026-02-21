# Fleet Hub (Django)

Digital fleet operations platform scaffolded in Django for:
- Fleet lifecycle and asset management
- Trip dispatch and validation workflows
- Maintenance and fuel/expense tracking
- Driver compliance and safety monitoring
- KPI and ROI analytics

## Quick Start (Windows PowerShell)

```powershell
cd e:\odoo_hakehon
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```

Open:
- App: http://127.0.0.1:8000/login/
- Admin: http://127.0.0.1:8000/admin/

## Production-Ready Stack

Included deployment components:
- PostgreSQL-ready database config via `DATABASE_URL`
- Gunicorn WSGI server
- WhiteNoise static files compression
- Docker image (`Dockerfile`)
- Docker Compose stack (`docker-compose.yml`) with:
  - `web` (Django + Gunicorn)
  - `db` (PostgreSQL)
  - `nginx` reverse proxy
- Nginx config: `deploy/nginx/default.conf`

### Run with Docker

```powershell
cd e:\odoo_hakehon
copy .env.example .env
docker compose up --build -d
```

Open:
- App: http://localhost/login/

### Important production settings

Set these in `.env` before live deployment:
- `DJANGO_SECRET_KEY`
- `DJANGO_DEBUG=False`
- `DJANGO_ALLOWED_HOSTS`
- `DJANGO_CSRF_TRUSTED_ORIGINS`
- `DATABASE_URL`
- SMTP email settings (`EMAIL_*`)
- TLS/cookie flags (`SECURE_SSL_REDIRECT`, `SESSION_COOKIE_SECURE`, `CSRF_COOKIE_SECURE`)

## Implemented Business Rules

- Trip assignment is blocked if `cargo_weight_kg > vehicle.max_load_capacity_kg`.
- Trip assignment is blocked if driver license is expired or wrong category.
- Suspended drivers cannot be assigned to trips.
- Opening a service log sets vehicle status to `In Shop`.
- Vehicles in `In Shop` or `Out of Service` are blocked from dispatch.
- Completing/canceling a trip returns driver and vehicle to available states (unless active service/out-of-service applies).
- Total operational cost per vehicle = fuel cost + maintenance cost.
