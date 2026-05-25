"""TESCAN VEGA3 Log Analyzer - Entry point.

Usage:
    python main.py              - Start GUI (default)
    python main.py --no-gui     - CLI mode only
    python main.py --import PATH - Import file or folder
    python main.py --backup     - Create database backup
    python main.py --verify     - Verify database integrity
"""

import argparse
import logging
import os
import shutil
import sys
from datetime import datetime

# Set up base path for imports
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from database.db_manager import DatabaseManager
from services.import_service import ImportService


def setup_logging(verbose: bool = False) -> None:
    """Configure application logging."""
    level = logging.DEBUG if verbose else logging.INFO
    log_format = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    logging.basicConfig(
        level=level,
        format=log_format,
        handlers=[
            logging.StreamHandler(sys.stdout),
        ],
    )


def get_db_path() -> str:
    """Get database file path."""
    data_dir = os.path.join(BASE_DIR, "data")
    os.makedirs(data_dir, exist_ok=True)
    return os.path.join(data_dir, "tescan_vega3.db")


def do_import(path: str, db: DatabaseManager) -> None:
    """Import a file or folder."""
    import_service = ImportService(db)

    if os.path.isdir(path):
        results = import_service.import_folder(path, operator="cli")
        for result in results:
            status = result.get("status", "unknown")
            file_name = result.get("file", "")
            message = result.get("message", "")
            print(f"  [{status}] {os.path.basename(file_name)}: {message}")
    elif os.path.isfile(path):
        result = import_service.import_file(path, operator="cli")
        print(f"  [{result['status']}] {result['message']}")
    else:
        print(f"Error: Path not found: {path}")
        sys.exit(1)


def do_backup(db: DatabaseManager) -> None:
    """Create a database backup."""
    backup_dir = os.path.join(BASE_DIR, "backups")
    os.makedirs(backup_dir, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = os.path.join(backup_dir, f"tescan_vega3_{timestamp}.db")

    try:
        shutil.copy2(db.db_path, backup_path)
        print(f"Backup created: {backup_path}")

        # Clean old backups (>30 days)
        _clean_old_backups(backup_dir, days=30)
    except OSError as e:
        print(f"Backup failed: {e}")
        sys.exit(1)


def _clean_old_backups(backup_dir: str, days: int = 30) -> None:
    """Remove backups older than specified days (keep monthly snapshots)."""
    now = datetime.now()
    removed = 0

    for filename in os.listdir(backup_dir):
        if not filename.endswith(".db"):
            continue
        filepath = os.path.join(backup_dir, filename)
        mtime = datetime.fromtimestamp(os.path.getmtime(filepath))
        age_days = (now - mtime).days

        # Keep monthly snapshots (first of month)
        if mtime.day == 1:
            continue

        if age_days > days:
            try:
                os.remove(filepath)
                removed += 1
            except OSError:
                pass

    if removed:
        print(f"  Cleaned {removed} old backup(s)")


def do_verify(db: DatabaseManager) -> None:
    """Verify database integrity."""
    with db.get_cursor() as cursor:
        cursor.execute("PRAGMA integrity_check")
        result = cursor.fetchone()
        status = result[0] if result else "unknown"

        if status == "ok":
            print("Database integrity: OK")
        else:
            print(f"Database integrity FAILED: {status}")
            sys.exit(1)

        # Show stats
        cursor.execute("SELECT COUNT(*) as cnt FROM sessions")
        sessions = cursor.fetchone()["cnt"]
        cursor.execute("SELECT COUNT(*) as cnt FROM hv_samples")
        hv_samples = cursor.fetchone()["cnt"]
        cursor.execute("SELECT COUNT(*) as cnt FROM vacuum_cycles")
        vacuum = cursor.fetchone()["cnt"]
        cursor.execute("SELECT COUNT(*) as cnt FROM file_cache")
        files = cursor.fetchone()["cnt"]

        print(f"  Sessions:      {sessions}")
        print(f"  HV samples:    {hv_samples}")
        print(f"  Vacuum cycles: {vacuum}")
        print(f"  Imported files: {files}")


def start_gui(db: DatabaseManager) -> None:
    """Start the GUI application."""
    try:
        # GUI module imports tkinter - only import when needed
        print("Starting TESCAN VEGA3 Log Analyzer GUI...")
        print("(GUI module not included in backend-only build)")
        print("Use --import, --backup, or --verify for CLI operations.")
    except ImportError as e:
        print(f"GUI startup failed: {e}")
        print("Run with --no-gui for CLI mode.")
        sys.exit(1)


def main() -> None:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="TESCAN VEGA3 Log Analyzer",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--import",
        dest="import_path",
        metavar="PATH",
        help="Import log file or scan folder recursively",
    )
    parser.add_argument(
        "--backup",
        action="store_true",
        help="Create database backup",
    )
    parser.add_argument(
        "--verify",
        action="store_true",
        help="Verify database integrity and show stats",
    )
    parser.add_argument(
        "--no-gui",
        action="store_true",
        help="CLI mode only (no GUI window)",
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Enable verbose logging",
    )

    args = parser.parse_args()
    setup_logging(verbose=args.verbose)

    # Initialize database
    db_path = get_db_path()
    db = DatabaseManager(db_path)
    db.initialize()

    try:
        if args.import_path:
            print(f"Importing: {args.import_path}")
            do_import(args.import_path, db)
        elif args.backup:
            do_backup(db)
        elif args.verify:
            do_verify(db)
        elif args.no_gui:
            print("TESCAN VEGA3 Log Analyzer - CLI mode")
            print("Use --import PATH to import log files")
            print("Use --backup to create database backup")
            print("Use --verify to check database integrity")
        else:
            # Auto-backup on start
            auto_backup = db.get_setting("auto_backup_on_start", "1")
            if auto_backup == "1":
                do_backup(db)
            start_gui(db)
    finally:
        db.close()


if __name__ == "__main__":
    main()
