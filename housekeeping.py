import os
from dataclasses import dataclass, field
from datetime import timedelta
from pathlib import Path

from flask import has_app_context

from config import Config
from models import Session, db, now


@dataclass
class CleanupResult:
    scanned_files: int = 0
    orphan_files: list[str] = field(default_factory=list)
    expired_referenced_files: list[str] = field(default_factory=list)
    missing_referenced_files: list[str] = field(default_factory=list)
    skipped_files: list[str] = field(default_factory=list)
    failed_files: dict[str, str] = field(default_factory=dict)
    cleared_photo_references: int = 0


def _safe_upload_file(upload_dir, filename):
    upload_root = Path(upload_dir).resolve()
    candidate = (upload_root / filename).resolve()
    if candidate.parent != upload_root:
        return None
    return candidate


def _is_allowed_photo(path):
    if not path.is_file():
        return False
    if path.name == '.gitkeep':
        return False
    return path.suffix.lower().lstrip('.') in Config.ALLOWED_EXTENSIONS


def _delete_file(path, result):
    try:
        path.unlink()
    except OSError as exc:
        result.failed_files[path.name] = str(exc)
        return False
    return True


def cleanup_uploaded_photos(
    app,
    dry_run=True,
    retention_days=90,
    orphan_grace_hours=24,
    current_time=None,
):
    current_time = current_time or now()
    if not has_app_context():
        with app.app_context():
            return cleanup_uploaded_photos(
                app,
                dry_run=dry_run,
                retention_days=retention_days,
                orphan_grace_hours=orphan_grace_hours,
                current_time=current_time,
            )

    upload_dir = Path(app.config['UPLOAD_FOLDER'])
    result = CleanupResult()

    if not upload_dir.exists():
        return result

    upload_files = {
        path.name: path
        for path in upload_dir.iterdir()
        if _is_allowed_photo(path)
    }
    result.scanned_files = len(upload_files)

    sessions = Session.query.filter(Session.photo_path.isnot(None)).all()
    sessions_by_photo = {}
    for session in sessions:
        sessions_by_photo.setdefault(session.photo_path, []).append(session)

    for filename in sorted(sessions_by_photo):
        if filename not in upload_files:
            result.missing_referenced_files.append(filename)

    orphan_cutoff = current_time - timedelta(hours=orphan_grace_hours)
    retention_cutoff = current_time - timedelta(days=retention_days)

    for filename, path in sorted(upload_files.items()):
        safe_path = _safe_upload_file(upload_dir, filename)
        if safe_path is None:
            result.skipped_files.append(filename)
            continue

        referencing_sessions = sessions_by_photo.get(filename, [])
        if not referencing_sessions:
            modified_at = current_time.__class__.fromtimestamp(path.stat().st_mtime)
            if modified_at <= orphan_cutoff:
                result.orphan_files.append(filename)
                if not dry_run:
                    _delete_file(safe_path, result)
            else:
                result.skipped_files.append(filename)
            continue

        all_references_expired = all(
            session.end_time <= retention_cutoff
            for session in referencing_sessions
        )
        if not all_references_expired:
            continue

        result.expired_referenced_files.append(filename)
        result.cleared_photo_references += len(referencing_sessions)
        if dry_run:
            continue

        deleted = _delete_file(safe_path, result)
        if deleted:
            for session in referencing_sessions:
                session.photo_path = None

    if not dry_run:
        db.session.commit()

    return result


def format_cleanup_result(result, dry_run=True):
    mode = 'dry-run' if dry_run else 'apply'
    lines = [
        f'mode={mode}',
        f'scanned_files={result.scanned_files}',
        f'orphan_files={len(result.orphan_files)}',
        f'expired_referenced_files={len(result.expired_referenced_files)}',
        f'cleared_photo_references={result.cleared_photo_references}',
        f'missing_referenced_files={len(result.missing_referenced_files)}',
        f'skipped_files={len(result.skipped_files)}',
        f'failed_files={len(result.failed_files)}',
    ]
    if result.orphan_files:
        lines.append('orphan_file_names=' + ','.join(result.orphan_files))
    if result.expired_referenced_files:
        lines.append('expired_referenced_file_names=' + ','.join(result.expired_referenced_files))
    if result.missing_referenced_files:
        lines.append('missing_referenced_file_names=' + ','.join(result.missing_referenced_files))
    if result.failed_files:
        failed = [f'{name}:{error}' for name, error in result.failed_files.items()]
        lines.append('failed_file_errors=' + ' | '.join(failed))
    return os.linesep.join(lines)
