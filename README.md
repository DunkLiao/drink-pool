# Drink Pool - 飲料團購系統

Internal drink ordering system for group purchases, built with Flask + SQLite.

## Tech Stack

- **Backend**: Python / Flask
- **Database**: SQLite (via Flask-SQLAlchemy)
- **Auth**: Flask-Login + bcrypt
- **Forms**: WTForms / Flask-WTF
- **Excel Export**: openpyxl
- **Frontend**: Bootstrap 5 (CDN)

## Quick Start

Double-click `start.bat` or run:

```powershell
pip install -r requirements.txt
python app.py
```

Open http://localhost:5001

## First-Time Setup

1. Visit `/admin/register` to create an admin account
2. Login at `/admin/login`
3. Go to "管理科別" to add departments (e.g. 信用風險, 市場風險)
4. Go to "新增場次" to create an ordering session:
   - Set title, upload order photo, define start/end time
5. Share the home page URL for colleagues to place orders

## Features

| Feature | Description |
|---------|-------------|
| Order Form | Name, department, drink item, sweetness, ice, add-ons (up to 5), notes |
| Session Management | Create/edit/delete ordering sessions with time window (down to minute) |
| Photo Upload | Upload order menu photos; displayed on the order form with click-to-zoom |
| Excel Export | Export session orders to formatted `.xlsx` with one click |
| Department Manager | CRUD + drag-sort ordering of departments |
| Site Settings | Customize footer text, site title, org name via admin panel |
| Database Restore | `restore_db.bat` to roll back to blank state |

## Directory Structure

```
drink-pool/
├── app.py                 # Flask application entry point
├── config.py              # App configuration
├── models.py              # Database models (6 tables)
├── forms.py               # WTForms definitions
├── utils.py               # Excel export helper
├── setup_db.py            # Database initialization script
├── rebuild_db.py          # Force-rebuild database from scratch
├── requirements.txt       # Python dependencies
├── start.bat              # One-click start (Windows)
├── restore_db.bat         # Restore database to blank state
├── db/
│   ├── drink_pool.db      # Working database (gitignored)
│   └── drink_pool_blank.db# Blank backup for restore (gitignored)
├── static/
│   ├── css/style.css
│   └── uploads/photos/    # Session order photos
└── templates/
    ├── base.html
    ├── index.html          # Public session list
    ├── order_form.html     # Order registration form
    ├── order_success.html
    └── admin/
        ├── login.html
        ├── register.html
        ├── dashboard.html
        ├── session_form.html
        ├── departments.html
        ├── orders.html
        └── settings.html
```

## Database Tables

| Table | Purpose |
|-------|---------|
| `users` | Admin accounts |
| `departments` | Configurable department list |
| `sessions` | Ordering sessions (time window, photo) |
| `orders` | Individual drink orders |
| `order_addons` | Per-order add-ons (max 5) |
| `system_settings` | Site configuration (key-value) |
