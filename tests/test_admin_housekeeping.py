import os
import tempfile
import unittest
from datetime import timedelta
from pathlib import Path

import bcrypt

from app import create_app
from models import Session, User, db, now


class AdminHousekeepingTest(unittest.TestCase):
    def setUp(self):
        self.original_database_url = os.environ.get('DATABASE_URL')
        self.original_admin_entry_password = os.environ.get('ADMIN_ENTRY_PASSWORD')
        os.environ['ADMIN_ENTRY_PASSWORD'] = 'entry-secret'

        self.db_file = tempfile.NamedTemporaryFile(suffix='.db', delete=False)
        self.db_file.close()
        db_path = self.db_file.name.replace(os.sep, '/')
        os.environ['DATABASE_URL'] = f'sqlite:///{db_path}'

        self.upload_dir = tempfile.TemporaryDirectory()
        self.app = create_app()
        self.app.config.update(
            TESTING=True,
            WTF_CSRF_ENABLED=False,
            UPLOAD_FOLDER=self.upload_dir.name,
        )

        with self.app.app_context():
            db.create_all()
            password_hash = bcrypt.hashpw(b'secret', bcrypt.gensalt()).decode('utf-8')
            db.session.add(User(username='admin', password_hash=password_hash))
            db.session.commit()

        self.client = self.app.test_client()

    def tearDown(self):
        with self.app.app_context():
            db.session.remove()
            db.drop_all()
            db.engine.dispose()

        self.upload_dir.cleanup()
        if self.original_database_url is None:
            os.environ.pop('DATABASE_URL', None)
        else:
            os.environ['DATABASE_URL'] = self.original_database_url

        if self.original_admin_entry_password is None:
            os.environ.pop('ADMIN_ENTRY_PASSWORD', None)
        else:
            os.environ['ADMIN_ENTRY_PASSWORD'] = self.original_admin_entry_password

        os.unlink(self.db_file.name)

    def login(self):
        self.client.post('/admin/entry', data={'password': 'entry-secret'})
        self.client.post('/admin/login', data={'username': 'admin', 'password': 'secret'})

    def write_photo(self, filename):
        path = Path(self.upload_dir.name) / filename
        path.write_bytes(b'image')
        modified_at = now() - timedelta(hours=48)
        timestamp = modified_at.timestamp()
        os.utime(path, (timestamp, timestamp))
        return path

    def add_expired_session(self, photo_path):
        current = now()
        with self.app.app_context():
            session = Session(
                title='過期場次',
                photo_path=photo_path,
                start_time=current - timedelta(days=120, hours=2),
                end_time=current - timedelta(days=120, hours=1),
                created_by=1,
            )
            db.session.add(session)
            db.session.commit()
            return session.id

    def test_dashboard_shows_housekeeping_button_for_logged_in_admin(self):
        self.login()

        response = self.client.get('/admin')

        self.assertEqual(response.status_code, 200)
        html = response.data.decode('utf-8')
        self.assertIn('清理圖片', html)
        self.assertIn('/admin/housekeeping', html)

    def test_housekeeping_requires_admin_login(self):
        response = self.client.post('/admin/housekeeping')

        self.assertEqual(response.status_code, 302)
        self.assertIn('/admin/login', response.headers['Location'])

    def test_admin_housekeeping_deletes_expired_photo_and_flashes_summary(self):
        self.login()
        self.write_photo('expired.png')
        session_id = self.add_expired_session('expired.png')

        response = self.client.post('/admin/housekeeping', follow_redirects=True)

        self.assertEqual(response.status_code, 200)
        self.assertFalse((Path(self.upload_dir.name) / 'expired.png').exists())
        self.assertIn('圖片清理完成'.encode('utf-8'), response.data)
        self.assertIn('掃描 1 個檔案'.encode('utf-8'), response.data)
        self.assertIn('過期引用 1 個'.encode('utf-8'), response.data)
        self.assertIn('清空引用 1 筆'.encode('utf-8'), response.data)
        with self.app.app_context():
            session = Session.query.get(session_id)
            self.assertIsNone(session.photo_path)


if __name__ == '__main__':
    unittest.main()
