import io
import os
import tempfile
import unittest
from unittest.mock import patch

import bcrypt

from app import create_app
from models import Session, User, db


class MenuOcrConfigTest(unittest.TestCase):
    def setUp(self):
        self.original_database_url = os.environ.get('DATABASE_URL')
        self.original_admin_entry_password = os.environ.get('ADMIN_ENTRY_PASSWORD')
        self.original_paddleocr_enabled = os.environ.get('PADDLEOCR_ENABLED')
        os.environ['ADMIN_ENTRY_PASSWORD'] = 'entry-secret'
        os.environ['PADDLEOCR_ENABLED'] = 'false'

        self.db_file = tempfile.NamedTemporaryFile(suffix='.db', delete=False)
        self.db_file.close()
        db_path = self.db_file.name.replace(os.sep, '/')
        os.environ['DATABASE_URL'] = f'sqlite:///{db_path}'

        self.app = create_app()
        self.app.config.update(
            TESTING=True,
            WTF_CSRF_ENABLED=False,
        )

        with self.app.app_context():
            db.create_all()
            password_hash = bcrypt.hashpw(b'secret', bcrypt.gensalt()).decode('utf-8')
            db.session.add(User(username='admin', password_hash=password_hash))
            db.session.commit()

        self.client = self.app.test_client()
        self.client.post('/admin/entry', data={'password': 'entry-secret'})
        self.client.post('/admin/login', data={'username': 'admin', 'password': 'secret'})

    def tearDown(self):
        with self.app.app_context():
            db.session.remove()
            db.drop_all()
            db.engine.dispose()

        if self.original_database_url is None:
            os.environ.pop('DATABASE_URL', None)
        else:
            os.environ['DATABASE_URL'] = self.original_database_url

        if self.original_admin_entry_password is None:
            os.environ.pop('ADMIN_ENTRY_PASSWORD', None)
        else:
            os.environ['ADMIN_ENTRY_PASSWORD'] = self.original_admin_entry_password

        if self.original_paddleocr_enabled is None:
            os.environ.pop('PADDLEOCR_ENABLED', None)
        else:
            os.environ['PADDLEOCR_ENABLED'] = self.original_paddleocr_enabled

        os.unlink(self.db_file.name)

    def test_disabled_ocr_does_not_import_uploaded_menu_photo(self):
        with patch('app.extract_menu_items_from_image', side_effect=AssertionError('OCR should be disabled')):
            response = self.client.post(
                '/admin/session/new',
                data={
                    'title': '午餐飲料',
                    'start_time': '2026-06-20T09:00',
                    'end_time': '2026-06-20T12:00',
                    'photo': (io.BytesIO(b'fake-image'), 'menu.png'),
                },
                content_type='multipart/form-data',
                follow_redirects=True,
            )

        self.assertEqual(response.status_code, 200)
        self.assertIn('OCR 未啟用'.encode('utf-8'), response.data)
        with self.app.app_context():
            session = Session.query.filter_by(title='午餐飲料').one()
            self.assertEqual(session.ocr_status, 'not_started')


if __name__ == '__main__':
    unittest.main()
