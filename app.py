import os
import json
import uuid
import hmac
import time
from concurrent.futures import ThreadPoolExecutor
from functools import wraps

from flask import Flask, render_template, request, redirect, url_for, flash, send_file, session as flask_session
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from sqlalchemy import inspect, text
from werkzeug.utils import secure_filename
import bcrypt

from config import Config, env_flag
from models import db, User, Department, AiMenuDraft, MenuItem, Session, Order, OrderAddon, SystemSetting, now
from forms import LoginForm, AdminEntryPasswordForm, RegisterForm, SessionForm, DepartmentForm, MenuItemForm, OrderForm, SettingsForm
from ai_menu import DEFAULT_OPENROUTER_MODEL, OpenRouterMenuCorrectionClient
from ocr import extract_menu_items_from_image, normalize_menu_name
from utils import export_orders_to_excel


def ensure_schema_upgrades():
    inspector = inspect(db.engine)
    if 'sessions' in inspector.get_table_names():
        session_columns = {column['name'] for column in inspector.get_columns('sessions')}
        session_column_defs = {
            'ocr_status': "ALTER TABLE sessions ADD COLUMN ocr_status VARCHAR(20) DEFAULT 'not_started'",
            'ocr_started_at': 'ALTER TABLE sessions ADD COLUMN ocr_started_at DATETIME',
            'ocr_completed_at': 'ALTER TABLE sessions ADD COLUMN ocr_completed_at DATETIME',
            'ocr_error': 'ALTER TABLE sessions ADD COLUMN ocr_error TEXT',
        }
        for column_name, sql in session_column_defs.items():
            if column_name not in session_columns:
                db.session.execute(text(sql))
        db.session.commit()

    if 'orders' in inspector.get_table_names():
        order_columns = {column['name'] for column in inspector.get_columns('orders')}
        if 'drink_price' not in order_columns:
            db.session.execute(text('ALTER TABLE orders ADD COLUMN drink_price INTEGER'))
            db.session.commit()


def menu_items_as_ai_candidates(session_id):
    items = MenuItem.query.filter_by(session_id=session_id).order_by(
        MenuItem.sort_order.asc(),
        MenuItem.name.asc(),
    ).all()
    return [{
        'name': item.name,
        'price': item.price,
        'ocr_confidence': item.ocr_confidence,
        'sort_order': item.sort_order,
    } for item in items]


def ai_draft_diagnostics(app, session_obj, candidates, started_at, exc=None):
    image_path = os.path.join(app.config['UPLOAD_FOLDER'], session_obj.photo_path or '')
    return {
        'model': app.config.get('OPENROUTER_MODEL') or DEFAULT_OPENROUTER_MODEL,
        'image_bytes': os.path.getsize(image_path) if os.path.exists(image_path) else None,
        'candidate_count': len(candidates),
        'duration_seconds': round(time.perf_counter() - started_at, 3),
        'error_type': type(exc).__name__ if exc else None,
        'upstream_detail': str(exc) if exc else None,
    }


def friendly_ai_error(exc):
    message = str(exc)
    if 'OpenRouter' in message or 'timed out' in message or 'timeout' in message.lower():
        return 'OpenRouter 回應異常，請稍後重試。'
    return 'AI 修正 OCR 失敗，請稍後重試或改用手動修正。'


def generate_ai_menu_draft(app, session_obj, candidates=None):
    image_path = os.path.join(app.config['UPLOAD_FOLDER'], session_obj.photo_path)
    if candidates is None:
        candidates = menu_items_as_ai_candidates(session_obj.id)
    client = OpenRouterMenuCorrectionClient(
        api_key=app.config.get('OPENROUTER_API_KEY'),
        model=app.config.get('OPENROUTER_MODEL') or DEFAULT_OPENROUTER_MODEL,
        site_url=app.config.get('OPENROUTER_SITE_URL'),
        site_name=app.config.get('OPENROUTER_SITE_NAME'),
        timeout=int(app.config.get('OPENROUTER_TIMEOUT_SECONDS', 90)),
        image_max_side=int(app.config.get('OPENROUTER_IMAGE_MAX_SIDE', 1200)),
    )
    return client.correct_menu(
        image_path=image_path,
        ocr_boxes=[],
        candidates=candidates,
        session_title=session_obj.title,
    )


def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)
    app.config['ADMIN_ENTRY_PASSWORD'] = os.environ.get('ADMIN_ENTRY_PASSWORD', app.config.get('ADMIN_ENTRY_PASSWORD'))
    app.config['OPENROUTER_API_KEY'] = os.environ.get('OPENROUTER_API_KEY')
    app.config['OPENROUTER_MODEL'] = os.environ.get('OPENROUTER_MODEL', app.config.get('OPENROUTER_MODEL'))
    app.config['OPENROUTER_SITE_URL'] = os.environ.get('OPENROUTER_SITE_URL', app.config.get('OPENROUTER_SITE_URL'))
    app.config['OPENROUTER_SITE_NAME'] = os.environ.get('OPENROUTER_SITE_NAME', app.config.get('OPENROUTER_SITE_NAME'))
    app.config['OPENROUTER_TIMEOUT_SECONDS'] = int(os.environ.get(
        'OPENROUTER_TIMEOUT_SECONDS',
        app.config.get('OPENROUTER_TIMEOUT_SECONDS', 90),
    ))
    app.config['OPENROUTER_IMAGE_MAX_SIDE'] = int(os.environ.get(
        'OPENROUTER_IMAGE_MAX_SIDE',
        app.config.get('OPENROUTER_IMAGE_MAX_SIDE', 1200),
    ))
    app.config['PADDLEOCR_ENABLED'] = env_flag('PADDLEOCR_ENABLED', Config.PADDLEOCR_ENABLED)
    app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get(
        'DATABASE_URL',
        app.config.get('SQLALCHEMY_DATABASE_URI'),
    )

    db.init_app(app)
    with app.app_context():
        db.create_all()
        ensure_schema_upgrades()

    login_manager = LoginManager()
    login_manager.init_app(app)
    login_manager.login_view = 'admin_login'
    login_manager.login_message = '請先登入後台。'

    @login_manager.user_loader
    def load_user(user_id):
        return User.query.get(int(user_id))

    # Ensure upload folder exists
    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
    app.extensions['menu_ocr_executor'] = ThreadPoolExecutor(max_workers=1)
    app.extensions['menu_ai_executor'] = ThreadPoolExecutor(max_workers=1)

    def save_uploaded_photo(photo):
        ext = os.path.splitext(secure_filename(photo.filename))[1]
        filename = f'{uuid.uuid4().hex}{ext}'
        photo.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
        return filename

    def import_menu_items_from_photo(session_obj):
        if not session_obj.photo_path:
            return 0

        image_path = os.path.join(app.config['UPLOAD_FOLDER'], session_obj.photo_path)
        recognized_items = extract_menu_items_from_image(image_path)
        existing_names = {
            normalize_menu_name(item.name)
            for item in MenuItem.query.filter_by(session_id=session_obj.id).all()
        }
        sort_order = MenuItem.query.filter_by(session_id=session_obj.id).count()
        imported_count = 0
        for item_data in recognized_items:
            normalized = normalize_menu_name(item_data['name'])
            if normalized in existing_names:
                continue
            db.session.add(MenuItem(
                session_id=session_obj.id,
                name=item_data['name'],
                price=item_data['price'],
                sort_order=sort_order,
                ocr_confidence=item_data.get('ocr_confidence'),
            ))
            existing_names.add(normalized)
            sort_order += 1
            imported_count += 1
        return imported_count

    def run_menu_ocr_job(session_id):
        with app.app_context():
            session_obj = Session.query.get(session_id)
            if not session_obj:
                return
            session_obj.ocr_status = 'running'
            session_obj.ocr_started_at = now()
            session_obj.ocr_completed_at = None
            session_obj.ocr_error = None
            db.session.commit()

            try:
                imported_count = import_menu_items_from_photo(session_obj)
                session_obj.ocr_status = 'done'
                session_obj.ocr_completed_at = now()
                session_obj.ocr_error = None
                db.session.commit()
                app.logger.info('PaddleOCR imported %s menu items for session %s', imported_count, session_id)
            except Exception as exc:
                db.session.rollback()
                failed_session = Session.query.get(session_id)
                if failed_session:
                    failed_session.ocr_status = 'failed'
                    failed_session.ocr_completed_at = now()
                    failed_session.ocr_error = str(exc)
                    db.session.commit()
                app.logger.warning('PaddleOCR import failed for session %s: %s', session_id, exc)

    def enqueue_menu_ocr(session_obj):
        session_obj.ocr_status = 'pending'
        session_obj.ocr_started_at = None
        session_obj.ocr_completed_at = None
        session_obj.ocr_error = None
        db.session.commit()

        if app.config.get('MENU_OCR_INLINE'):
            run_menu_ocr_job(session_obj.id)
        else:
            app.extensions['menu_ocr_executor'].submit(run_menu_ocr_job, session_obj.id)

    def run_menu_ocr(session_obj):
        if not app.config.get('PADDLEOCR_ENABLED'):
            session_obj.ocr_status = 'not_started'
            session_obj.ocr_started_at = None
            session_obj.ocr_completed_at = None
            session_obj.ocr_error = None
            db.session.commit()
            flash('OCR 未啟用，請先手動新增菜單品項；若要使用 OCR，請安裝 requirements-ocr.txt 並設定 PADDLEOCR_ENABLED=true。', 'warning')
            return

        try:
            enqueue_menu_ocr(session_obj)
        except Exception as exc:
            app.logger.warning('PaddleOCR import failed for session %s: %s', session_obj.id, exc)
            flash(f'OCR 辨識失敗：{exc}', 'warning')
            return

        flash('OCR 已排入背景辨識，完成後可到菜單品項頁查看。', 'info')

    def run_ai_menu_draft_job(draft_id):
        with app.app_context():
            draft = AiMenuDraft.query.get(draft_id)
            if not draft:
                return
            session_obj = Session.query.get(draft.session_id)
            if not session_obj:
                return
            candidates = menu_items_as_ai_candidates(session_obj.id)
            started_at = time.perf_counter()
            draft.status = 'running'
            draft.error = None
            draft.raw_payload = json.dumps(
                ai_draft_diagnostics(app, session_obj, candidates, started_at),
                ensure_ascii=False,
            )
            db.session.commit()

            try:
                result = generate_ai_menu_draft(app, session_obj, candidates=candidates)
                draft.status = 'pending'
                draft.raw_payload = json.dumps(result, ensure_ascii=False)
                draft.suggested_items = json.dumps(result.get('items', []), ensure_ascii=False)
                draft.rejected_texts = json.dumps(result.get('rejected_texts', []), ensure_ascii=False)
                draft.error = None
                db.session.commit()
            except Exception as exc:
                db.session.rollback()
                failed_draft = AiMenuDraft.query.get(draft_id)
                failed_session = Session.query.get(session_obj.id)
                if failed_draft and failed_session:
                    failed_draft.status = 'failed'
                    failed_draft.error = friendly_ai_error(exc)
                    failed_draft.raw_payload = json.dumps(
                        ai_draft_diagnostics(app, failed_session, candidates, started_at, exc),
                        ensure_ascii=False,
                    )
                    failed_draft.suggested_items = '[]'
                    failed_draft.rejected_texts = '[]'
                    db.session.commit()
                app.logger.exception('AI menu draft failed for session %s draft %s', session_obj.id, draft_id)

    # -------------------- Admin required decorator --------------------
    def admin_required(f):
        @wraps(f)
        @login_required
        def decorated(*args, **kwargs):
            return f(*args, **kwargs)
        return decorated

    def admin_entry_verified():
        return current_user.is_authenticated or flask_session.get('admin_entry_verified') is True

    def current_path_with_query():
        query = request.query_string.decode('utf-8')
        return f'{request.path}?{query}' if query else request.path

    def safe_admin_next(next_page):
        if not next_page:
            return None
        if next_page.startswith('/admin') and not next_page.startswith('//'):
            return next_page
        return None

    def require_admin_entry():
        if admin_entry_verified():
            return None
        if not app.config.get('ADMIN_ENTRY_PASSWORD'):
            flash('尚未設定 ADMIN_ENTRY_PASSWORD 環境變數，無法進入後台。', 'danger')
        return redirect(url_for('admin_entry', next=current_path_with_query()))

    # -------------------- Context processor --------------------
    @app.context_processor
    def inject_settings():
        settings = {}
        for key in Config.DEFAULT_SETTINGS:
            settings[key] = SystemSetting.get(key, Config.DEFAULT_SETTINGS[key])
        return {'settings': settings}

    # -------------------- Public routes --------------------
    @app.route('/')
    def index():
        open_sessions = Session.query.filter(
            Session.is_active == True,
            Session.start_time <= now(),
            Session.end_time >= now(),
        ).order_by(Session.end_time.asc()).all()
        return render_template('index.html', sessions=open_sessions)

    @app.route('/order/<int:session_id>')
    def order_form(session_id):
        session_obj = Session.query.get_or_404(session_id)
        if not session_obj.is_open:
            flash('此團購場次已結束或尚未開始，無法報名。', 'warning')
            return redirect(url_for('index'))

        departments = Department.query.order_by(Department.sort_order).all()
        form = OrderForm()
        form.department.choices = [(d.id, d.name) for d in departments]
        form.sweetness.choices = Config.SWEETNESS_CHOICES
        form.ice.choices = Config.ICE_CHOICES
        menu_items = MenuItem.query.filter_by(
            session_id=session_id,
            is_active=True,
        ).order_by(MenuItem.sort_order.asc(), MenuItem.name.asc()).all()
        return render_template('order_form.html', form=form, session=session_obj, menu_items=menu_items)

    @app.route('/order/<int:session_id>', methods=['POST'])
    def order_submit(session_id):
        session_obj = Session.query.get_or_404(session_id)
        if not session_obj.is_open:
            flash('此團購場次已結束或尚未開始，無法報名。', 'warning')
            return redirect(url_for('index'))

        departments = Department.query.order_by(Department.sort_order).all()
        form = OrderForm()
        form.department.choices = [(d.id, d.name) for d in departments]
        form.sweetness.choices = Config.SWEETNESS_CHOICES
        form.ice.choices = Config.ICE_CHOICES

        if not form.validate_on_submit():
            menu_items = MenuItem.query.filter_by(
                session_id=session_id,
                is_active=True,
            ).order_by(MenuItem.sort_order.asc(), MenuItem.name.asc()).all()
            return render_template('order_form.html', form=form, session=session_obj, menu_items=menu_items)

        selected_item = None
        menu_item_id = request.form.get('menu_item_id')
        if menu_item_id:
            selected_item = MenuItem.query.filter_by(
                id=menu_item_id,
                session_id=session_obj.id,
                is_active=True,
            ).first()

        drink_item = selected_item.name if selected_item else form.drink_item.data.strip()
        drink_price = selected_item.price if selected_item else None

        order = Order(
            session_id=session_obj.id,
            name=form.name.data.strip(),
            department_id=form.department.data,
            drink_item=drink_item,
            drink_price=drink_price,
            sweetness=form.sweetness.data,
            ice=form.ice.data,
            notes=form.notes.data.strip() if form.notes.data else None,
        )
        db.session.add(order)
        db.session.flush()

        # Process addons (up to 5)
        addon_values = [a.strip() for a in request.form.getlist('addons') if a.strip()]
        addon_values = addon_values[:Config.MAX_ADDONS]
        for i, addon in enumerate(addon_values):
            db.session.add(OrderAddon(order_id=order.id, addon_name=addon, sort_order=i))

        db.session.commit()
        flash('訂單已成功送出！', 'success')
        return render_template('order_success.html', order=order, session=session_obj)

    # -------------------- Admin: Auth --------------------
    @app.route('/admin/entry', methods=['GET', 'POST'])
    def admin_entry():
        if current_user.is_authenticated:
            return redirect(url_for('admin_dashboard'))

        form = AdminEntryPasswordForm()
        entry_password = app.config.get('ADMIN_ENTRY_PASSWORD')

        if form.validate_on_submit():
            if entry_password and hmac.compare_digest(form.password.data, entry_password):
                flask_session['admin_entry_verified'] = True
                flash('入口密碼驗證成功，請登入管理員帳號。', 'success')
                next_page = safe_admin_next(request.args.get('next'))
                return redirect(next_page or url_for('admin_login'))
            flash('後台入口密碼錯誤。', 'danger')

        return render_template('admin/entry.html', form=form, entry_password_configured=bool(entry_password))

    @app.route('/admin/login', methods=['GET', 'POST'])
    def admin_login():
        if current_user.is_authenticated:
            return redirect(url_for('admin_dashboard'))
        entry_redirect = require_admin_entry()
        if entry_redirect:
            return entry_redirect
        form = LoginForm()
        if form.validate_on_submit():
            user = User.query.filter_by(username=form.username.data).first()
            if user and bcrypt.checkpw(form.password.data.encode('utf-8'), user.password_hash.encode('utf-8')):
                login_user(user)
                flash('登入成功。', 'success')
                next_page = request.args.get('next')
                return redirect(next_page or url_for('admin_dashboard'))
            flash('帳號或密碼錯誤。', 'danger')
        return render_template('admin/login.html', form=form)

    @app.route('/admin/register', methods=['GET', 'POST'])
    def admin_register():
        if current_user.is_authenticated:
            return redirect(url_for('admin_dashboard'))
        entry_redirect = require_admin_entry()
        if entry_redirect:
            return entry_redirect
        form = RegisterForm()
        if form.validate_on_submit():
            if User.query.filter_by(username=form.username.data).first():
                flash('此帳號已存在。', 'danger')
            else:
                pw_hash = bcrypt.hashpw(form.password.data.encode('utf-8'), bcrypt.gensalt())
                user = User(username=form.username.data, password_hash=pw_hash.decode('utf-8'))
                db.session.add(user)
                db.session.commit()
                flash('註冊成功，請登入。', 'success')
                return redirect(url_for('admin_login'))
        return render_template('admin/register.html', form=form)

    @app.route('/admin/logout')
    @login_required
    def admin_logout():
        logout_user()
        flask_session.pop('admin_entry_verified', None)
        flash('已登出。', 'info')
        return redirect(url_for('index'))

    # -------------------- Admin: Dashboard --------------------
    @app.route('/admin')
    @admin_required
    def admin_dashboard():
        sessions = Session.query.order_by(Session.created_at.desc()).all()
        return render_template('admin/dashboard.html', sessions=sessions, now=now())

    # -------------------- Admin: Sessions --------------------
    @app.route('/admin/session/new', methods=['GET', 'POST'])
    @admin_required
    def admin_session_new():
        form = SessionForm()
        if form.validate_on_submit():
            photo_path = None
            if form.photo.data:
                photo_path = save_uploaded_photo(form.photo.data)

            session_obj = Session(
                title=form.title.data.strip(),
                photo_path=photo_path,
                start_time=form.start_time.data,
                end_time=form.end_time.data,
                created_by=current_user.id,
            )
            db.session.add(session_obj)
            db.session.flush()
            db.session.commit()
            if photo_path:
                run_menu_ocr(session_obj)
            flash('團購場次已建立。', 'success')
            return redirect(url_for('admin_dashboard'))
        return render_template('admin/session_form.html', form=form, editing=False)

    @app.route('/admin/session/<int:session_id>/edit', methods=['GET', 'POST'])
    @admin_required
    def admin_session_edit(session_id):
        session_obj = Session.query.get_or_404(session_id)
        form = SessionForm(obj=session_obj)
        if form.validate_on_submit():
            session_obj.title = form.title.data.strip()
            session_obj.start_time = form.start_time.data
            session_obj.end_time = form.end_time.data

            if form.photo.data:
                # Delete old photo if exists
                if session_obj.photo_path:
                    old_path = os.path.join(app.config['UPLOAD_FOLDER'], session_obj.photo_path)
                    if os.path.exists(old_path):
                        os.remove(old_path)
                session_obj.photo_path = save_uploaded_photo(form.photo.data)
                db.session.commit()
                run_menu_ocr(session_obj)

            db.session.commit()
            flash('場次已更新。', 'success')
            return redirect(url_for('admin_dashboard'))
        return render_template('admin/session_form.html', form=form, editing=True, session=session_obj)

    @app.route('/admin/session/<int:session_id>/delete', methods=['POST'])
    @admin_required
    def admin_session_delete(session_id):
        session_obj = Session.query.get_or_404(session_id)
        # Delete photo file
        if session_obj.photo_path:
            photo_path = os.path.join(app.config['UPLOAD_FOLDER'], session_obj.photo_path)
            if os.path.exists(photo_path):
                os.remove(photo_path)
        db.session.delete(session_obj)
        db.session.commit()
        flash('場次已刪除。', 'info')
        return redirect(url_for('admin_dashboard'))

    @app.route('/admin/session/<int:session_id>/toggle', methods=['POST'])
    @admin_required
    def admin_session_toggle(session_id):
        session_obj = Session.query.get_or_404(session_id)
        session_obj.is_active = not session_obj.is_active
        db.session.commit()
        status = '啟用' if session_obj.is_active else '停用'
        flash(f'場次已{status}。', 'info')
        return redirect(url_for('admin_dashboard'))

    # -------------------- Admin: Menu Items --------------------
    @app.route('/admin/session/<int:session_id>/menu', methods=['GET', 'POST'])
    @admin_required
    def admin_session_menu(session_id):
        session_obj = Session.query.get_or_404(session_id)
        form = MenuItemForm()
        if form.validate_on_submit():
            normalized = normalize_menu_name(form.name.data)
            duplicate = next(
                (
                    item for item in MenuItem.query.filter_by(session_id=session_id).all()
                    if normalize_menu_name(item.name) == normalized
                ),
                None,
            )
            if duplicate:
                flash('此品項已存在。', 'danger')
            else:
                sort_order = MenuItem.query.filter_by(session_id=session_id).count()
                item = MenuItem(
                    session_id=session_id,
                    name=form.name.data.strip(),
                    price=form.price.data,
                    sort_order=sort_order,
                )
                db.session.add(item)
                db.session.commit()
                flash('菜單品項已新增。', 'success')
                return redirect(url_for('admin_session_menu', session_id=session_id))

        menu_items = MenuItem.query.filter_by(session_id=session_id).order_by(
            MenuItem.sort_order.asc(),
            MenuItem.name.asc(),
        ).all()
        ai_drafts = AiMenuDraft.query.filter_by(session_id=session_id).order_by(
            AiMenuDraft.created_at.desc(),
        ).limit(5).all()
        ai_active = any(draft.status in ('queued', 'running') for draft in ai_drafts)
        ai_can_run = (
            bool(app.config.get('OPENROUTER_API_KEY'))
            and bool(session_obj.photo_path)
            and session_obj.ocr_status == 'done'
            and bool(menu_items)
            and not ai_active
        )
        return render_template(
            'admin/menu_items.html',
            session=session_obj,
            form=form,
            menu_items=menu_items,
            ai_drafts=ai_drafts,
            ai_enabled=bool(app.config.get('OPENROUTER_API_KEY')),
            ai_can_run=ai_can_run,
            ai_active=ai_active,
        )

    @app.route('/admin/menu-item/<int:item_id>/edit', methods=['POST'])
    @admin_required
    def admin_menu_item_edit(item_id):
        item = MenuItem.query.get_or_404(item_id)
        name = request.form.get('name', '').strip()
        price_raw = request.form.get('price', '').strip()
        if not name:
            flash('請輸入品項名稱。', 'danger')
            return redirect(url_for('admin_session_menu', session_id=item.session_id))
        try:
            price = int(price_raw)
        except ValueError:
            flash('價格需為整數。', 'danger')
            return redirect(url_for('admin_session_menu', session_id=item.session_id))
        if price < 0 or price > 9999:
            flash('價格需介於 0 到 9999。', 'danger')
            return redirect(url_for('admin_session_menu', session_id=item.session_id))

        duplicate = next(
            (
                other for other in MenuItem.query.filter_by(session_id=item.session_id).all()
                if other.id != item.id and normalize_menu_name(other.name) == normalize_menu_name(name)
            ),
            None,
        )
        if duplicate:
            flash('此品項已存在。', 'danger')
            return redirect(url_for('admin_session_menu', session_id=item.session_id))

        item.name = name
        item.price = price
        db.session.commit()
        flash('菜單品項已更新。', 'success')
        return redirect(url_for('admin_session_menu', session_id=item.session_id))

    @app.route('/admin/menu-item/<int:item_id>/toggle', methods=['POST'])
    @admin_required
    def admin_menu_item_toggle(item_id):
        item = MenuItem.query.get_or_404(item_id)
        item.is_active = not item.is_active
        db.session.commit()
        flash('菜單品項狀態已更新。', 'info')
        return redirect(url_for('admin_session_menu', session_id=item.session_id))

    @app.route('/admin/menu-item/<int:item_id>/delete', methods=['POST'])
    @admin_required
    def admin_menu_item_delete(item_id):
        item = MenuItem.query.get_or_404(item_id)
        session_id = item.session_id
        db.session.delete(item)
        db.session.commit()
        flash('菜單品項已刪除。', 'info')
        return redirect(url_for('admin_session_menu', session_id=session_id))

    @app.route('/admin/menu-item/<int:item_id>/sort', methods=['POST'])
    @admin_required
    def admin_menu_item_sort(item_id):
        item = MenuItem.query.get_or_404(item_id)
        direction = request.form.get('direction', 'down')
        items = MenuItem.query.filter_by(session_id=item.session_id).order_by(MenuItem.sort_order.asc(), MenuItem.id.asc()).all()
        current_idx = next((i for i, candidate in enumerate(items) if candidate.id == item.id), None)
        if current_idx is not None:
            if direction == 'up' and current_idx > 0:
                items[current_idx].sort_order, items[current_idx - 1].sort_order = items[current_idx - 1].sort_order, items[current_idx].sort_order
            elif direction == 'down' and current_idx < len(items) - 1:
                items[current_idx].sort_order, items[current_idx + 1].sort_order = items[current_idx + 1].sort_order, items[current_idx].sort_order
            db.session.commit()
        return redirect(url_for('admin_session_menu', session_id=item.session_id))

    @app.route('/admin/session/<int:session_id>/menu/ocr', methods=['POST'])
    @admin_required
    def admin_session_menu_ocr(session_id):
        session_obj = Session.query.get_or_404(session_id)
        if not session_obj.photo_path:
            flash('此場次尚未上傳菜單照片。', 'warning')
        else:
            run_menu_ocr(session_obj)
        return redirect(url_for('admin_session_menu', session_id=session_id))

    @app.route('/admin/session/<int:session_id>/menu/ai-draft', methods=['POST'])
    @admin_required
    def admin_session_menu_ai_draft(session_id):
        session_obj = Session.query.get_or_404(session_id)
        if not session_obj.photo_path:
            flash('此場次尚未上傳菜單照片。', 'warning')
            return redirect(url_for('admin_session_menu', session_id=session_id))
        if not app.config.get('OPENROUTER_API_KEY'):
            flash('尚未設定 OPENROUTER_API_KEY，無法使用 AI 修正 OCR。', 'warning')
            return redirect(url_for('admin_session_menu', session_id=session_id))
        if session_obj.ocr_status != 'done':
            flash('請先完成 OCR 或手動新增品項，再執行 AI 修正。', 'warning')
            return redirect(url_for('admin_session_menu', session_id=session_id))
        if not MenuItem.query.filter_by(session_id=session_id).first():
            flash('請先完成 OCR 或手動新增品項，再執行 AI 修正。', 'warning')
            return redirect(url_for('admin_session_menu', session_id=session_id))
        active_draft = AiMenuDraft.query.filter(
            AiMenuDraft.session_id == session_id,
            AiMenuDraft.status.in_(('queued', 'running')),
        ).first()
        if active_draft:
            flash('AI 修正已在執行中，請稍後重新整理此頁查看結果。', 'info')
            return redirect(url_for('admin_session_menu', session_id=session_id))

        draft = AiMenuDraft(
            session_id=session_id,
            raw_payload='{}',
            suggested_items='[]',
            rejected_texts='[]',
            status='queued',
        )
        db.session.add(draft)
        db.session.commit()
        app.extensions['menu_ai_executor'].submit(run_ai_menu_draft_job, draft.id)
        flash('AI 修正已排入背景處理，完成後可重新整理查看草稿。', 'info')
        return redirect(url_for('admin_session_menu', session_id=session_id))

    @app.route('/admin/session/<int:session_id>/menu/ai-draft/<int:draft_id>/apply', methods=['POST'])
    @admin_required
    def admin_session_menu_ai_draft_apply(session_id, draft_id):
        draft = AiMenuDraft.query.filter_by(id=draft_id, session_id=session_id).first_or_404()
        if draft.status != 'pending':
            flash('此 AI 草稿已處理，無法重複套用。', 'warning')
            return redirect(url_for('admin_session_menu', session_id=session_id))

        selected_indexes = {
            int(value)
            for value in request.form.getlist('item_index')
            if value.isdigit()
        }
        try:
            suggested_items = json.loads(draft.suggested_items)
        except json.JSONDecodeError:
            suggested_items = []

        existing_items = MenuItem.query.filter_by(session_id=session_id).all()
        existing_by_name = {
            normalize_menu_name(item.name): item
            for item in existing_items
        }
        sort_order = len(existing_items)
        applied_count = 0
        for index, item_data in enumerate(suggested_items):
            if index not in selected_indexes:
                continue
            name = str(item_data.get('name', '')).strip()
            try:
                price = int(item_data.get('price'))
            except (TypeError, ValueError):
                continue
            if not name or price < 0 or price > 9999:
                continue

            normalized = normalize_menu_name(name)
            if normalized in existing_by_name:
                item = existing_by_name[normalized]
                item.price = price
                item.ocr_confidence = item_data.get('confidence')
            else:
                item = MenuItem(
                    session_id=session_id,
                    name=name,
                    price=price,
                    sort_order=sort_order,
                    ocr_confidence=item_data.get('confidence'),
                )
                db.session.add(item)
                existing_by_name[normalized] = item
                sort_order += 1
            applied_count += 1

        draft.status = 'applied'
        draft.applied_at = now()
        db.session.commit()
        flash(f'已套用 {applied_count} 筆 AI 草稿品項。', 'success')
        return redirect(url_for('admin_session_menu', session_id=session_id))

    # -------------------- Admin: Orders --------------------
    @app.route('/admin/session/<int:session_id>/orders')
    @admin_required
    def admin_session_orders(session_id):
        session_obj = Session.query.get_or_404(session_id)
        orders = Order.query.filter_by(session_id=session_id).order_by(Order.created_at.asc()).all()
        return render_template('admin/orders.html', session=session_obj, orders=orders)

    # -------------------- Admin: Departments --------------------
    @app.route('/admin/departments', methods=['GET', 'POST'])
    @admin_required
    def admin_departments():
        form = DepartmentForm()
        if form.validate_on_submit():
            name = form.name.data.strip()
            if Department.query.filter_by(name=name).first():
                flash('此科別已存在。', 'danger')
            else:
                dept = Department(name=name)
                db.session.add(dept)
                db.session.commit()
                flash('科別已新增。', 'success')
                return redirect(url_for('admin_departments'))
        departments = Department.query.order_by(Department.sort_order).all()
        return render_template('admin/departments.html', form=form, departments=departments)

    @app.route('/admin/department/<int:dept_id>/delete', methods=['POST'])
    @admin_required
    def admin_department_delete(dept_id):
        dept = Department.query.get_or_404(dept_id)
        # Check if any orders reference this department
        if Order.query.filter_by(department_id=dept_id).first():
            flash('此科別已有訂單記錄，無法刪除。', 'danger')
        else:
            db.session.delete(dept)
            db.session.commit()
            flash('科別已刪除。', 'info')
        return redirect(url_for('admin_departments'))

    @app.route('/admin/department/<int:dept_id>/sort', methods=['POST'])
    @admin_required
    def admin_department_sort(dept_id):
        dept = Department.query.get_or_404(dept_id)
        direction = request.form.get('direction', 'down')
        depts = Department.query.order_by(Department.sort_order).all()
        current_idx = next((i for i, d in enumerate(depts) if d.id == dept_id), None)
        if current_idx is not None:
            if direction == 'up' and current_idx > 0:
                depts[current_idx].sort_order, depts[current_idx - 1].sort_order = \
                    depts[current_idx - 1].sort_order, depts[current_idx].sort_order
            elif direction == 'down' and current_idx < len(depts) - 1:
                depts[current_idx].sort_order, depts[current_idx + 1].sort_order = \
                    depts[current_idx + 1].sort_order, depts[current_idx].sort_order
            db.session.commit()
        return redirect(url_for('admin_departments'))

    # -------------------- Admin: Settings --------------------
    @app.route('/admin/settings', methods=['GET', 'POST'])
    @admin_required
    def admin_settings():
        form = SettingsForm()
        if form.validate_on_submit():
            for key in Config.DEFAULT_SETTINGS:
                SystemSetting.set(key, form[key].data.strip())
            db.session.commit()
            flash('網站設定已儲存。', 'success')
            return redirect(url_for('admin_settings'))

        if request.method == 'GET':
            for key in Config.DEFAULT_SETTINGS:
                form[key].data = SystemSetting.get(key, Config.DEFAULT_SETTINGS[key])
        return render_template('admin/settings.html', form=form)

    # -------------------- Admin: Export --------------------
    @app.route('/admin/session/<int:session_id>/export')
    @admin_required
    def admin_session_export(session_id):
        session_obj = Session.query.get_or_404(session_id)
        output = export_orders_to_excel(session_obj)
        filename = f'團購訂單_{session_obj.title}_{now().strftime("%Y%m%d")}.xlsx'
        return send_file(
            output,
            as_attachment=True,
            download_name=filename,
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        )

    return app


if __name__ == '__main__':
    app = create_app()
    with app.app_context():
        db.create_all()
    app.run(debug=True, use_reloader=False, port=5001)
