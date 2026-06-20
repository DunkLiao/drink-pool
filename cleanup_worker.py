import os
import sys
import time
from datetime import datetime, timedelta

from app import create_app
from config import env_flag
from housekeeping import cleanup_uploaded_photos, format_cleanup_result


def _next_run_at(current_time, run_at):
    hour, minute = [int(part) for part in run_at.split(':', 1)]
    candidate = current_time.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if candidate <= current_time:
        candidate += timedelta(days=1)
    return candidate


def _sleep_seconds(current_time, run_at, interval_hours):
    if run_at:
        return max(1, int((_next_run_at(current_time, run_at) - current_time).total_seconds()))
    return max(60, int(interval_hours * 3600))


def run_once(app):
    retention_days = int(os.environ.get('UPLOAD_CLEANUP_RETENTION_DAYS', '90'))
    orphan_grace_hours = int(os.environ.get('UPLOAD_CLEANUP_ORPHAN_GRACE_HOURS', '24'))
    with app.app_context():
        result = cleanup_uploaded_photos(
            app,
            dry_run=False,
            retention_days=retention_days,
            orphan_grace_hours=orphan_grace_hours,
        )
        print(format_cleanup_result(result, dry_run=False), flush=True)
        return result


def run_worker_loop(
    app,
    interval_hours,
    run_at,
    now_func=datetime.now,
    sleep_func=time.sleep,
    run_once_func=run_once,
    max_runs=None,
):
    completed_runs = 0
    while max_runs is None or completed_runs < max_runs:
        seconds = _sleep_seconds(now_func(), run_at, interval_hours)
        print(f'next_cleanup_in_seconds={seconds}', flush=True)
        sleep_func(seconds)
        run_once_func(app)
        completed_runs += 1


def main():
    if not env_flag('UPLOAD_CLEANUP_ENABLED', False):
        print('UPLOAD_CLEANUP_ENABLED is not true; cleanup worker is idle.', flush=True)
        return 0

    app = create_app()
    interval_hours = float(os.environ.get('UPLOAD_CLEANUP_INTERVAL_HOURS', '24'))
    run_at = os.environ.get('UPLOAD_CLEANUP_RUN_AT', '').strip()
    run_worker_loop(app, interval_hours=interval_hours, run_at=run_at)


if __name__ == '__main__':
    sys.exit(main())
