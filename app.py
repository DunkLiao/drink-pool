import os
import uuid
import hmac
from datetime import datetime, timezone
from functools import wraps

from flask import Flask, render_template, request, redirect, url_for, flash, send_file, session as flask_session
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from werkzeug.utils import secure_filename
import bcrypt

from config import Config
from models import db, User, Department, Session, Order, OrderAddon, SystemSetting, now
from forms import LoginForm, AdminEntryPasswordForm, RegisterForm, SessionForm, DepartmentForm, OrderForm, SettingsForm
from utils import export_orders_to_excel


def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)
    app.config['ADMIN_ENTRY_PASSWORD'] = os.environ.get('ADMIN_ENTRY_PASSWORD', app.config.get('ADMIN_ENTRY_PASSWORD'))
    app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get(
        'DATABASE_URL',
        app.config.get('SQLALCHEMY_DATABASE_URI'),
    )

    db.init_app(app)

    login_manager = LoginManager()
    login_manager.init_app(app)
    login_manager.login_view = 'admin_login'
    login_manager.login_message = '請先登入後台。'

    @login_manager.user_loader
    def load_user(user_id):
        return User.query.get(int(user_id))

    # Ensure upload folder exists
    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

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
        return render_template('order_form.html', form=form, session=session_obj)

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
            return render_template('order_form.html', form=form, session=session_obj)

        order = Order(
            session_id=session_obj.id,
            name=form.name.data.strip(),
            department_id=form.department.data,
            drink_item=form.drink_item.data.strip(),
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
                photo = form.photo.data
                ext = os.path.splitext(secure_filename(photo.filename))[1]
                filename = f'{uuid.uuid4().hex}{ext}'
                photo.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
                photo_path = filename

            session_obj = Session(
                title=form.title.data.strip(),
                photo_path=photo_path,
                start_time=form.start_time.data,
                end_time=form.end_time.data,
                created_by=current_user.id,
            )
            db.session.add(session_obj)
            db.session.commit()
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
                photo = form.photo.data
                ext = os.path.splitext(secure_filename(photo.filename))[1]
                filename = f'{uuid.uuid4().hex}{ext}'
                photo.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
                session_obj.photo_path = filename

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
        filename = f'團購訂單_{session_obj.title}_{datetime.now().strftime("%Y%m%d")}.xlsx'
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
    app.run(debug=True, port=5001)
