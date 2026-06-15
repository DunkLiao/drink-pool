import os
import tempfile
import unittest

from app import create_app
from models import db


class AdminEntryPasswordTest(unittest.TestCase):
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

        self.client = self.app.test_client()

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

    def test_admin_login_requires_entry_password_first(self):
        response = self.client.get('/admin/login')

        self.assertEqual(response.status_code, 302)
        self.assertIn('/admin/entry', response.headers['Location'])

    def test_wrong_entry_password_stays_on_entry_page(self):
        response = self.client.post('/admin/entry', data={'password': 'wrong'})

        self.assertEqual(response.status_code, 200)

        with self.client.session_transaction() as session:
            self.assertFalse(session.get('admin_entry_verified'))

    def test_correct_entry_password_allows_admin_login_page(self):
        response = self.client.post('/admin/entry', data={'password': 'entry-secret'})

        self.assertEqual(response.status_code, 302)
        self.assertIn('/admin/login', response.headers['Location'])

        login_response = self.client.get('/admin/login')

        self.assertEqual(login_response.status_code, 200)
        self.assertIn('後台登入'.encode('utf-8'), login_response.data)


class MissingAdminEntryPasswordTest(unittest.TestCase):
    def setUp(self):
        self.original_password = os.environ.get('ADMIN_ENTRY_PASSWORD')
        self.original_database_url = os.environ.get('DATABASE_URL')
        os.environ.pop('ADMIN_ENTRY_PASSWORD', None)
        self.db_file = tempfile.NamedTemporaryFile(suffix='.db', delete=False)
        self.db_file.close()
        db_path = self.db_file.name.replace(os.sep, '/')
        os.environ['DATABASE_URL'] = f'sqlite:///{db_path}'

        self.app = create_app()
        self.app.config.update(
            TESTING=True,
            WTF_CSRF_ENABLED=False,
            ADMIN_ENTRY_PASSWORD=None,
        )

        with self.app.app_context():
            db.create_all()

        self.client = self.app.test_client()

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

    def test_missing_entry_password_blocks_admin_login(self):
        response = self.client.get('/admin/login', follow_redirects=True)

        self.assertEqual(response.status_code, 200)
        self.assertIn('尚未設定 ADMIN_ENTRY_PASSWORD'.encode('utf-8'), response.data)


if __name__ == '__main__':
    unittest.main()
