import os
import tempfile
import unittest
from datetime import timedelta

from app import create_app
from models import Department, Session, User, db, now


class OrderPhotoTemplateTest(unittest.TestCase):
    def setUp(self):
        self.original_database_url = os.environ.get('DATABASE_URL')
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
            user = User(username='admin', password_hash='hash')
            department = Department(name='風管部', sort_order=1)
            session = Session(
                title='團購一',
                photo_path='menu.png',
                start_time=now() - timedelta(minutes=5),
                end_time=now() + timedelta(minutes=30),
                created_by=1,
            )
            db.session.add_all([user, department, session])
            db.session.commit()
            self.session_id = session.id

        self.client = self.app.test_client()

    def tearDown(self):
        with self.app.app_context():
            db.session.remove()
            db.drop_all()
            db.engine.dispose()

        if self.original_database_url is None:
            os.environ.pop('DATABASE_URL', None)
        else:
            os.environ['DATABASE_URL'] = self.original_database_url
        os.unlink(self.db_file.name)

    def test_order_photo_can_be_downloaded_and_preview_keeps_ratio(self):
        response = self.client.get(f'/order/{self.session_id}')

        self.assertEqual(response.status_code, 200)
        html = response.data.decode('utf-8')
        self.assertIn('download="menu.png"', html)
        self.assertIn('class="order-photo-preview', html)
        self.assertIn('class="order-photo-modal-image', html)


if __name__ == '__main__':
    unittest.main()
