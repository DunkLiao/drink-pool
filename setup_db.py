import os
import sys
import shutil

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)

from app import create_app
from config import Config
from models import db, SystemSetting

app = create_app()

with app.app_context():
    db_dir = os.path.join(BASE_DIR, 'db')
    os.makedirs(db_dir, exist_ok=True)

    db.create_all()

    # Seed default settings
    for key, value in Config.DEFAULT_SETTINGS.items():
        if not SystemSetting.query.filter_by(key=key).first():
            SystemSetting.set(key, value)

    db.session.commit()

    # Create blank backup for restore on first initialization.
    db_path = os.path.join(db_dir, 'drink_pool.db')
    blank_path = os.path.join(db_dir, 'drink_pool_blank.db')
    if not os.path.exists(blank_path):
        shutil.copy2(db_path, blank_path)

    print('Database initialized: db/drink_pool.db')
    print('Blank backup available: db/drink_pool_blank.db')
