import os
import tempfile
import unittest
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import patch

import bcrypt
from openpyxl import load_workbook

from app import create_app
from models import Session, User, db
from utils import export_orders_to_excel


class HostDatetime(datetime):
    @classmethod
    def now(cls, tz=None):
        return cls(2026, 6, 21, 0, 30, 0)


def taipei_now():
    return datetime(2026, 6, 20, 23, 30, 0)


class ExcelExportTimezoneTest(unittest.TestCase):
    def setUp(self):
        self.original_password = os.environ.get('ADMIN_ENTRY_PASSWORD')
        self.original_database_url = os.environ.get('DATABASE_URL')
        os.environ['ADMIN_ENTRY_PASSWORD'] = 'entry-secret'
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
            user = User(username='admin', password_hash=password_hash)
            session = Session(
                title='台北日期測試',
                start_time=datetime(2026, 6, 20, 9, 0),
                end_time=datetime(2026, 6, 20, 12, 0),
                created_by=1,
            )
            db.session.add_all([user, session])
            db.session.commit()
            self.session_id = session.id

        self.client = self.app.test_client()
        self.client.post('/admin/entry', data={'password': 'entry-secret'})
        self.client.post('/admin/login', data={'username': 'admin', 'password': 'secret'})

    def tearDown(self):
        with self.app.app_context():
            db.session.remove()
            db.drop_all()
            db.engine.dispose()

        if self.original_password is None:
            os.environ.pop('ADMIN_ENTRY_PASSWORD', None)
        else:
            os.environ['ADMIN_ENTRY_PASSWORD'] = self.original_password

        if self.original_database_url is None:
            os.environ.pop('DATABASE_URL', None)
        else:
            os.environ['DATABASE_URL'] = self.original_database_url

        os.unlink(self.db_file.name)

    def test_export_filename_uses_taipei_date_instead_of_host_date(self):
        with patch('app.datetime', HostDatetime, create=True), patch('app.now', taipei_now):
            response = self.client.get(f'/admin/session/{self.session_id}/export')

        self.assertEqual(response.status_code, 200)
        content_disposition = response.headers['Content-Disposition']
        self.assertIn('20260620', content_disposition)
        self.assertNotIn('20260621', content_disposition)

    def test_export_workbook_uses_taipei_export_time_instead_of_host_time(self):
        session = SimpleNamespace(
            title='台北日期測試',
            start_time=datetime(2026, 6, 20, 9, 0),
            end_time=datetime(2026, 6, 20, 12, 0),
            orders=[],
        )

        with patch('utils.datetime', HostDatetime, create=True), patch('utils.now', taipei_now):
            output = export_orders_to_excel(session)

        workbook = load_workbook(output)
        info_text = workbook.active['A2'].value

        self.assertIn('匯出時間：2026/06/20 23:30:00', info_text)
        self.assertNotIn('2026/06/21 00:30:00', info_text)


if __name__ == '__main__':
    unittest.main()
