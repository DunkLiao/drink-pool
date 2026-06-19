from datetime import datetime, timezone, timedelta
import json
from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin

db = SQLAlchemy()

TAIPEI = timezone(timedelta(hours=8))


def now():
    return datetime.now(TAIPEI).replace(tzinfo=None)


class User(UserMixin, db.Model):
    __tablename__ = 'users'

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(128), nullable=False)
    created_at = db.Column(db.DateTime, default=now)

    sessions = db.relationship('Session', backref='creator', lazy=True)


class Department(db.Model):
    __tablename__ = 'departments'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), unique=True, nullable=False)
    sort_order = db.Column(db.Integer, default=0)
    created_at = db.Column(db.DateTime, default=now)


class Session(db.Model):
    __tablename__ = 'sessions'

    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    photo_path = db.Column(db.String(500))
    start_time = db.Column(db.DateTime, nullable=False)
    end_time = db.Column(db.DateTime, nullable=False)
    is_active = db.Column(db.Boolean, default=True)
    ocr_status = db.Column(db.String(20), default='not_started')
    ocr_started_at = db.Column(db.DateTime)
    ocr_completed_at = db.Column(db.DateTime)
    ocr_error = db.Column(db.Text)
    created_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=now)

    orders = db.relationship('Order', backref='session', lazy=True, cascade='all, delete-orphan')
    menu_items = db.relationship('MenuItem', backref='session', lazy=True, cascade='all, delete-orphan')

    @property
    def is_open(self):
        n = now()
        return self.is_active and self.start_time <= n <= self.end_time


class MenuItem(db.Model):
    __tablename__ = 'menu_items'

    id = db.Column(db.Integer, primary_key=True)
    session_id = db.Column(db.Integer, db.ForeignKey('sessions.id'), nullable=False)
    name = db.Column(db.String(200), nullable=False)
    price = db.Column(db.Integer, nullable=False)
    sort_order = db.Column(db.Integer, default=0)
    is_active = db.Column(db.Boolean, default=True)
    ocr_confidence = db.Column(db.Float)
    created_at = db.Column(db.DateTime, default=now)
    updated_at = db.Column(db.DateTime, default=now, onupdate=now)


class AiMenuDraft(db.Model):
    __tablename__ = 'ai_menu_drafts'

    id = db.Column(db.Integer, primary_key=True)
    session_id = db.Column(db.Integer, db.ForeignKey('sessions.id'), nullable=False)
    raw_payload = db.Column(db.Text, nullable=False, default='{}')
    suggested_items = db.Column(db.Text, nullable=False, default='[]')
    rejected_texts = db.Column(db.Text, nullable=False, default='[]')
    status = db.Column(db.String(20), nullable=False, default='pending')
    error = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=now)
    applied_at = db.Column(db.DateTime)

    @property
    def suggested_item_list(self):
        try:
            return json.loads(self.suggested_items)
        except json.JSONDecodeError:
            return []

    @property
    def rejected_text_list(self):
        try:
            return json.loads(self.rejected_texts)
        except json.JSONDecodeError:
            return []


class Order(db.Model):
    __tablename__ = 'orders'

    id = db.Column(db.Integer, primary_key=True)
    session_id = db.Column(db.Integer, db.ForeignKey('sessions.id'), nullable=False)
    name = db.Column(db.String(100), nullable=False)
    department_id = db.Column(db.Integer, db.ForeignKey('departments.id'), nullable=False)
    drink_item = db.Column(db.String(200), nullable=False)
    drink_price = db.Column(db.Integer)
    sweetness = db.Column(db.String(20), nullable=False)
    ice = db.Column(db.String(20), nullable=False)
    notes = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=now)

    department = db.relationship('Department', lazy=True)
    addons = db.relationship('OrderAddon', backref='order', lazy=True, cascade='all, delete-orphan')


class OrderAddon(db.Model):
    __tablename__ = 'order_addons'

    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.Integer, db.ForeignKey('orders.id'), nullable=False)
    addon_name = db.Column(db.String(100), nullable=False)
    sort_order = db.Column(db.Integer, default=0)


class SystemSetting(db.Model):
    __tablename__ = 'system_settings'

    id = db.Column(db.Integer, primary_key=True)
    key = db.Column(db.String(100), unique=True, nullable=False)
    value = db.Column(db.Text, nullable=False, default='')
    updated_at = db.Column(db.DateTime, default=now, onupdate=now)

    @staticmethod
    def get(key, default=''):
        setting = SystemSetting.query.filter_by(key=key).first()
        return setting.value if setting else default

    @staticmethod
    def set(key, value):
        setting = SystemSetting.query.filter_by(key=key).first()
        if setting:
            setting.value = value
        else:
            setting = SystemSetting(key=key, value=value)
            db.session.add(setting)
        db.session.commit()
