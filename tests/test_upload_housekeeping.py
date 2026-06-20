import os
import tempfile
import unittest
from datetime import timedelta
from pathlib import Path

from app import create_app
from housekeeping import cleanup_uploaded_photos
from models import Session, User, db, now


class UploadHousekeepingTest(unittest.TestCase):
    def setUp(self):
        self.original_database_url = os.environ.get('DATABASE_URL')
        self.db_file = tempfile.NamedTemporaryFile(suffix='.db', delete=False)
        self.db_file.close()
        db_path = self.db_file.name.replace(os.sep, '/')
        os.environ['DATABASE_URL'] = f'sqlite:///{db_path}'

        self.upload_dir = tempfile.TemporaryDirectory()
        self.app = create_app()
        self.app.config.update(
            TESTING=True,
            UPLOAD_FOLDER=self.upload_dir.name,
        )

        with self.app.app_context():
            db.create_all()
            db.session.add(User(username='admin', password_hash='hash'))
            db.session.commit()

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
        os.unlink(self.db_file.name)

    def write_photo(self, filename, age_hours=48):
        path = Path(self.upload_dir.name) / filename
        path.write_bytes(b'image')
        modified_at = now() - timedelta(hours=age_hours)
        timestamp = modified_at.timestamp()
        os.utime(path, (timestamp, timestamp))
        return path

    def add_session(self, photo_path, ended_days_ago=0, active=True):
        current = now()
        session = Session(
            title=f'session-{photo_path}-{ended_days_ago}',
            photo_path=photo_path,
            start_time=current - timedelta(days=ended_days_ago, hours=2),
            end_time=current - timedelta(days=ended_days_ago, hours=1),
            is_active=active,
            created_by=1,
        )
        db.session.add(session)
        db.session.commit()
        return session

    def test_dry_run_does_not_delete_files_or_clear_database_references(self):
        self.write_photo('old-menu.png')
        with self.app.app_context():
            session = self.add_session('old-menu.png', ended_days_ago=120)

            result = cleanup_uploaded_photos(self.app, dry_run=True, retention_days=90)

            db.session.refresh(session)
            self.assertTrue((Path(self.upload_dir.name) / 'old-menu.png').exists())
            self.assertEqual(session.photo_path, 'old-menu.png')
            self.assertEqual(result.expired_referenced_files, ['old-menu.png'])
            self.assertEqual(result.cleared_photo_references, 1)

    def test_deletes_old_orphan_photo_after_grace_period(self):
        self.write_photo('orphan.jpg', age_hours=48)

        result = cleanup_uploaded_photos(
            self.app,
            dry_run=False,
            retention_days=90,
            orphan_grace_hours=24,
        )

        self.assertFalse((Path(self.upload_dir.name) / 'orphan.jpg').exists())
        self.assertEqual(result.orphan_files, ['orphan.jpg'])

    def test_keeps_recent_orphan_photo_during_grace_period(self):
        self.write_photo('recent.webp', age_hours=2)

        result = cleanup_uploaded_photos(
            self.app,
            dry_run=False,
            retention_days=90,
            orphan_grace_hours=24,
        )

        self.assertTrue((Path(self.upload_dir.name) / 'recent.webp').exists())
        self.assertEqual(result.orphan_files, [])
        self.assertEqual(result.skipped_files, ['recent.webp'])

    def test_deletes_expired_session_photo_and_clears_reference(self):
        self.write_photo('expired.jpeg')
        with self.app.app_context():
            session = self.add_session('expired.jpeg', ended_days_ago=120)

            result = cleanup_uploaded_photos(self.app, dry_run=False, retention_days=90)

            db.session.refresh(session)
            self.assertFalse((Path(self.upload_dir.name) / 'expired.jpeg').exists())
            self.assertIsNone(session.photo_path)
            self.assertEqual(result.expired_referenced_files, ['expired.jpeg'])
            self.assertEqual(result.cleared_photo_references, 1)

    def test_keeps_photo_for_session_within_retention_window(self):
        self.write_photo('recent-session.png')
        with self.app.app_context():
            session = self.add_session('recent-session.png', ended_days_ago=30)

            result = cleanup_uploaded_photos(self.app, dry_run=False, retention_days=90)

            db.session.refresh(session)
            self.assertTrue((Path(self.upload_dir.name) / 'recent-session.png').exists())
            self.assertEqual(session.photo_path, 'recent-session.png')
            self.assertEqual(result.expired_referenced_files, [])

    def test_keeps_shared_photo_when_any_session_is_still_within_retention(self):
        self.write_photo('shared.gif')
        with self.app.app_context():
            expired = self.add_session('shared.gif', ended_days_ago=120)
            recent = self.add_session('shared.gif', ended_days_ago=30)

            result = cleanup_uploaded_photos(self.app, dry_run=False, retention_days=90)

            db.session.refresh(expired)
            db.session.refresh(recent)
            self.assertTrue((Path(self.upload_dir.name) / 'shared.gif').exists())
            self.assertEqual(expired.photo_path, 'shared.gif')
            self.assertEqual(recent.photo_path, 'shared.gif')
            self.assertEqual(result.expired_referenced_files, [])

    def test_ignores_gitkeep_subdirectories_and_unknown_extensions(self):
        (Path(self.upload_dir.name) / '.gitkeep').write_text('', encoding='utf-8')
        (Path(self.upload_dir.name) / 'nested').mkdir()
        self.write_photo('notes.txt')

        result = cleanup_uploaded_photos(self.app, dry_run=False)

        self.assertTrue((Path(self.upload_dir.name) / '.gitkeep').exists())
        self.assertTrue((Path(self.upload_dir.name) / 'nested').is_dir())
        self.assertTrue((Path(self.upload_dir.name) / 'notes.txt').exists())
        self.assertEqual(result.scanned_files, 0)

    def test_missing_referenced_file_is_reported_without_clearing_database(self):
        with self.app.app_context():
            session = self.add_session('missing.png', ended_days_ago=120)

            result = cleanup_uploaded_photos(self.app, dry_run=False, retention_days=90)

            db.session.refresh(session)
            self.assertEqual(session.photo_path, 'missing.png')
            self.assertEqual(result.missing_referenced_files, ['missing.png'])


if __name__ == '__main__':
    unittest.main()
