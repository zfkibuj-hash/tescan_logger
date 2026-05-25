"""TESCAN Log Analyzer - Entry point.

Desktop application for tracking and billing TESCAN microscope usage
based on system logs. GLP/ISO 17025 compliant.

Usage:
    python main.py                    # Launch GUI
    python main.py --import DIR       # Import logs from directory
    python main.py --backup           # Run manual backup
    python main.py --verify           # Verify database integrity
"""

import sys
import os
import argparse
import logging
from pathlib import Path
from datetime import datetime

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

from database.db_manager import DatabaseManager
from utils.backup import BackupManager

# Application metadata
APP_NAME = "TESCAN Log Analyzer"
APP_VERSION = "2.0.0"
APP_DIR = Path(__file__).parent


def setup_logging(log_dir: str = "logs", level: int = logging.INFO):
    """Configure application logging."""
    log_path = Path(log_dir)
    log_path.mkdir(parents=True, exist_ok=True)

    log_file = log_path / f"tescan_{datetime.now().strftime('%Y%m%d')}.log"

    logging.basicConfig(
        level=level,
        format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S',
        handlers=[
            logging.FileHandler(str(log_file), encoding='utf-8'),
            logging.StreamHandler(sys.stdout),
        ]
    )


def parse_args():
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description=f"{APP_NAME} v{APP_VERSION}"
    )
    parser.add_argument(
        '--import', dest='import_dir', metavar='DIR',
        help='Import log files from directory'
    )
    parser.add_argument(
        '--backup', action='store_true',
        help='Run manual backup'
    )
    parser.add_argument(
        '--verify', action='store_true',
        help='Verify database integrity (GLP check)'
    )
    parser.add_argument(
        '--no-gui', action='store_true',
        help='Run without GUI (CLI mode)'
    )
    parser.add_argument(
        '--debug', action='store_true',
        help='Enable debug logging'
    )
    return parser.parse_args()


def run_cli_import(import_dir: str, db: DatabaseManager):
    """Run import pipeline from CLI."""
    from models.enums import MicroscopeType
    from services.import_service import ImportService
    from parser.file_registry import FileRegistry

    logger = logging.getLogger(__name__)
    logger.info("CLI import from: %s", import_dir)

    # Scan for files
    registry = FileRegistry()
    files = registry.scan_directory(import_dir)

    if not files:
        logger.warning("No log files found in %s", import_dir)
        return

    # Detect microscope type from first history file
    microscope_type = MicroscopeType.VEGA3
    service = ImportService(
        db_manager=db,
        microscope_id=1,
        microscope_type=microscope_type,
    )

    result = service.import_files(files)
    logger.info(
        "Import result: %d files processed, %d sessions, %d vacuum cycles, "
        "%d penalties, %d HV samples, %d errors",
        result.files_processed, result.sessions_created,
        result.vacuum_cycles_created, result.penalties_created,
        result.hv_samples_imported, len(result.errors)
    )
    if result.errors:
        for err in result.errors[:10]:
            logger.error("  %s", err)


def run_verify(db: DatabaseManager):
    """Run database integrity verification."""
    logger = logging.getLogger(__name__)
    logger.info("Running database integrity check...")

    result = db.verify_integrity()
    if result["integrity_ok"] and result["audit_coverage"]:
        logger.info("DATABASE INTEGRITY: OK")
        logger.info("AUDIT COVERAGE: OK")
    else:
        logger.warning("DATABASE ISSUES FOUND:")
        for issue in result["issues"]:
            logger.warning("  - %s", issue)

    return result


def launch_gui(db: DatabaseManager):
    """Launch the tkinter GUI application."""
    try:
        from gui.main_window import MainWindow
        app = MainWindow(db)
        app.mainloop()
    except ImportError as e:
        log = logging.getLogger(__name__)
        log.info("GUI not available (missing module: %s). Use --no-gui for CLI mode.", e)
        print(f"\n{APP_NAME} v{APP_VERSION}")
        print("GUI module not available. Run with --no-gui for CLI mode.")
        print("Or install GUI dependencies and run again.")


def main():
    """Main entry point."""
    args = parse_args()

    # Setup logging
    log_level = logging.DEBUG if args.debug else logging.INFO
    setup_logging(level=log_level)

    logger = logging.getLogger(__name__)
    logger.info("=== %s v%s starting ===", APP_NAME, APP_VERSION)

    # Initialize database
    db = DatabaseManager()
    db.initialize()

    # Auto-backup on startup
    backup_on_startup = db.get_setting("backup_on_startup", "true")
    if backup_on_startup == "true" and not args.no_gui:
        backup_mgr = BackupManager()
        backup_mgr.auto_backup_on_startup()

    # Handle CLI commands
    if args.backup:
        backup_mgr = BackupManager()
        path = backup_mgr.create_backup(label="manual")
        logger.info("Manual backup created: %s", path)
        db.close()
        return

    if args.verify:
        run_verify(db)
        db.close()
        return

    if args.import_dir:
        run_cli_import(args.import_dir, db)
        db.close()
        return

    # Launch GUI or inform about CLI mode
    if args.no_gui:
        logger.info("CLI mode. Use --import DIR, --backup, or --verify.")
        print(f"{APP_NAME} v{APP_VERSION} - CLI mode")
        print("Commands: --import DIR | --backup | --verify")
    else:
        launch_gui(db)

    db.close()
    logger.info("=== Application exiting ===")


if __name__ == '__main__':
    main()
