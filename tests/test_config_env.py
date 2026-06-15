import os
import tempfile
import unittest

from config import load_env_file


class DotEnvLoadingTest(unittest.TestCase):
    def setUp(self):
        self.original_password = os.environ.get('ADMIN_ENTRY_PASSWORD')
        os.environ.pop('ADMIN_ENTRY_PASSWORD', None)

    def tearDown(self):
        if self.original_password is None:
            os.environ.pop('ADMIN_ENTRY_PASSWORD', None)
        else:
            os.environ['ADMIN_ENTRY_PASSWORD'] = self.original_password

    def test_load_env_file_sets_admin_entry_password(self):
        with tempfile.NamedTemporaryFile('w', encoding='utf-8', delete=False) as env_file:
            env_file.write('ADMIN_ENTRY_PASSWORD=local-uat-secret\n')
            env_path = env_file.name

        try:
            load_env_file(env_path)

            self.assertEqual(os.environ.get('ADMIN_ENTRY_PASSWORD'), 'local-uat-secret')
        finally:
            os.unlink(env_path)

    def test_load_env_file_does_not_override_existing_environment(self):
        os.environ['ADMIN_ENTRY_PASSWORD'] = 'existing-secret'

        with tempfile.NamedTemporaryFile('w', encoding='utf-8', delete=False) as env_file:
            env_file.write('ADMIN_ENTRY_PASSWORD=env-file-secret\n')
            env_path = env_file.name

        try:
            load_env_file(env_path)

            self.assertEqual(os.environ.get('ADMIN_ENTRY_PASSWORD'), 'existing-secret')
        finally:
            os.unlink(env_path)


if __name__ == '__main__':
    unittest.main()
