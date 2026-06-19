import sqlite3
import os

DB_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'db')
DB_PATH = os.path.join(DB_DIR, 'drink_pool.db')
BLANK_PATH = os.path.join(DB_DIR, 'drink_pool_blank.db')

os.makedirs(DB_DIR, exist_ok=True)

# Drop and recreate from scratch
if os.path.exists(DB_PATH):
    os.remove(DB_PATH)
if os.path.exists(BLANK_PATH):
    os.remove(BLANK_PATH)

conn = sqlite3.connect(DB_PATH)
conn.executescript("""
CREATE TABLE users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username VARCHAR(80) UNIQUE NOT NULL,
    password_hash VARCHAR(128) NOT NULL,
    created_at DATETIME
);

CREATE TABLE departments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name VARCHAR(100) UNIQUE NOT NULL,
    sort_order INTEGER DEFAULT 0,
    created_at DATETIME
);

CREATE TABLE sessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title VARCHAR(200) NOT NULL,
    photo_path VARCHAR(500),
    start_time DATETIME NOT NULL,
    end_time DATETIME NOT NULL,
    is_active BOOLEAN DEFAULT 1,
    ocr_status VARCHAR(20) DEFAULT 'not_started',
    ocr_started_at DATETIME,
    ocr_completed_at DATETIME,
    ocr_error TEXT,
    created_by INTEGER NOT NULL,
    created_at DATETIME,
    FOREIGN KEY (created_by) REFERENCES users (id)
);

CREATE TABLE orders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id INTEGER NOT NULL,
    name VARCHAR(100) NOT NULL,
    department_id INTEGER NOT NULL,
    drink_item VARCHAR(200) NOT NULL,
    drink_price INTEGER,
    sweetness VARCHAR(20) NOT NULL,
    ice VARCHAR(20) NOT NULL,
    notes TEXT,
    created_at DATETIME,
    FOREIGN KEY (session_id) REFERENCES sessions (id),
    FOREIGN KEY (department_id) REFERENCES departments (id)
);

CREATE TABLE menu_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id INTEGER NOT NULL,
    name VARCHAR(200) NOT NULL,
    price INTEGER NOT NULL,
    sort_order INTEGER DEFAULT 0,
    is_active BOOLEAN DEFAULT 1,
    ocr_confidence FLOAT,
    created_at DATETIME,
    updated_at DATETIME,
    FOREIGN KEY (session_id) REFERENCES sessions (id)
);

CREATE TABLE ai_menu_drafts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id INTEGER NOT NULL,
    raw_payload TEXT NOT NULL DEFAULT '{}',
    suggested_items TEXT NOT NULL DEFAULT '[]',
    rejected_texts TEXT NOT NULL DEFAULT '[]',
    status VARCHAR(20) NOT NULL DEFAULT 'pending',
    error TEXT,
    created_at DATETIME,
    applied_at DATETIME,
    FOREIGN KEY (session_id) REFERENCES sessions (id)
);

CREATE TABLE order_addons (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    order_id INTEGER NOT NULL,
    addon_name VARCHAR(100) NOT NULL,
    sort_order INTEGER DEFAULT 0,
    FOREIGN KEY (order_id) REFERENCES orders (id)
);

CREATE TABLE system_settings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    key VARCHAR(100) UNIQUE NOT NULL,
    value TEXT NOT NULL DEFAULT '',
    updated_at DATETIME
);

INSERT INTO system_settings (key, value) VALUES
    ('site_title', '飲料團購系統'),
    ('site_subtitle', '臺灣銀行 風險管理部 飲料團購系統'),
    ('org_name', '臺灣銀行'),
    ('org_dept', '風險管理部');
""")
conn.commit()
conn.close()

# Copy to blank backup
import shutil
shutil.copy2(DB_PATH, BLANK_PATH)

# Verify
for name in ['drink_pool.db', 'drink_pool_blank.db']:
    c = sqlite3.connect(os.path.join(DB_DIR, name))
    users = c.execute('SELECT COUNT(*) FROM users').fetchone()[0]
    tables = c.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
    c.close()
    print(f'{name}: {len(tables)} tables, {users} users')

print('Done - blank backup is clean.')
