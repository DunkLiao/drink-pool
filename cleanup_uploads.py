import argparse
import sys

from app import create_app
from housekeeping import cleanup_uploaded_photos, format_cleanup_result


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description='Clean uploaded menu photos.')
    action = parser.add_mutually_exclusive_group()
    action.add_argument('--dry-run', action='store_true', help='Preview cleanup without deleting files.')
    action.add_argument('--yes', action='store_true', help='Delete files and clear expired database references.')
    parser.add_argument('--retention-days', type=int, default=90, help='Days to keep photos after a session ends.')
    parser.add_argument('--orphan-grace-hours', type=int, default=24, help='Hours to keep unreferenced uploads before deletion.')
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    dry_run = not args.yes

    app = create_app()
    with app.app_context():
        result = cleanup_uploaded_photos(
            app,
            dry_run=dry_run,
            retention_days=args.retention_days,
            orphan_grace_hours=args.orphan_grace_hours,
        )
        print(format_cleanup_result(result, dry_run=dry_run))
        return 1 if result.failed_files else 0


if __name__ == '__main__':
    sys.exit(main())
