import unittest
from datetime import datetime

from cleanup_worker import run_worker_loop


class CleanupWorkerScheduleTest(unittest.TestCase):
    def test_worker_waits_until_configured_run_at_before_first_cleanup(self):
        calls = []

        run_worker_loop(
            app='fake-app',
            interval_hours=24,
            run_at='03:30',
            now_func=lambda: datetime(2026, 6, 20, 1, 0),
            sleep_func=lambda seconds: calls.append(('sleep', seconds)),
            run_once_func=lambda app: calls.append(('run', app)),
            max_runs=1,
        )

        self.assertEqual(calls, [
            ('sleep', 9000),
            ('run', 'fake-app'),
        ])


if __name__ == '__main__':
    unittest.main()
