"""Backup manager - rolling backups + monthly snapshots.

Features:
- Auto-backup on application startup (configurable)
- Rolling: delete backups older than N days (default 30)
- Monthly snapshots: tescan_monthly_YYYY-MM.db (kept indefinitely)
- Manual backup from Settings
"""

import shutil
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import List

logger = logging.getLogger(__name__)

DEFAULT_BACKUP_DIR = "backups"
DEFAULT_RETENTION_DAYS = 30


class BackupManager:
    """Manages database backups with rolling retention."""

    def __init__(
        self,
        db_path: str = "tescan_logger.db",
        hv_db_path: str = "tescan_hv.db",
        backup_dir: str = DEFAULT_BACKUP_DIR,
        retention_days: int = DEFAULT_RETENTION_DAYS,
    ):
        self.db_path = Path(db_path)
        self.hv_db_path = Path(hv_db_path)
        self.backup_dir = Path(backup_dir)
        self.retention_days = retention_days

    def create_backup(self, label: str = "") -> str:
        """Create a backup of both databases.

        Args:
            label: Optional label for the backup filename.

        Returns:
            Path to the backup file.
        """
        self.backup_dir.mkdir(parents=True, exist_ok=True)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        suffix = f"_{label}" if label else ""

        # Backup main DB
        main_backup = self.backup_dir / f"tescan_{timestamp}{suffix}.db"
        if self.db_path.exists():
            shutil.copy2(str(self.db_path), str(main_backup))
            logger.info("Main DB backup: %s", main_backup)

        # Backup HV DB
        hv_backup = self.backup_dir / f"tescan_hv_{timestamp}{suffix}.db"
        if self.hv_db_path.exists():
            shutil.copy2(str(self.hv_db_path), str(hv_backup))
            logger.info("HV DB backup: %s", hv_backup)

        return str(main_backup)

    def create_monthly_snapshot(self) -> str:
        """Create monthly snapshot (kept indefinitely)."""
        month_str = datetime.now().strftime("%Y-%m")
        snapshot_name = f"tescan_monthly_{month_str}.db"
        snapshot_path = self.backup_dir / snapshot_name

        if snapshot_path.exists():
            logger.info("Monthly snapshot already exists: %s", snapshot_path)
            return str(snapshot_path)

        self.backup_dir.mkdir(parents=True, exist_ok=True)
        if self.db_path.exists():
            shutil.copy2(str(self.db_path), str(snapshot_path))
            logger.info("Monthly snapshot created: %s", snapshot_path)

        return str(snapshot_path)

    def cleanup_old_backups(self) -> int:
        """Remove rolling backups older than retention_days.

        Monthly snapshots (tescan_monthly_*) are never deleted.

        Returns:
            Number of files removed.
        """
        if not self.backup_dir.exists():
            return 0

        cutoff = datetime.now() - timedelta(days=self.retention_days)
        removed = 0

        for f in self.backup_dir.iterdir():
            if not f.is_file():
                continue
            # Never delete monthly snapshots
            if "monthly" in f.name:
                continue
            # Check file modification time
            mtime = datetime.fromtimestamp(f.stat().st_mtime)
            if mtime < cutoff:
                f.unlink()
                removed += 1
                logger.info("Removed old backup: %s", f.name)

        if removed:
            logger.info("Cleaned up %d old backups", removed)
        return removed

    def auto_backup_on_startup(self) -> None:
        """Run auto-backup sequence on application startup."""
        logger.info("Running auto-backup on startup...")
        self.create_backup(label="auto")
        self.create_monthly_snapshot()
        self.cleanup_old_backups()

    def list_backups(self) -> List[dict]:
        """List all existing backups with metadata."""
        if not self.backup_dir.exists():
            return []

        backups = []
        for f in sorted(self.backup_dir.iterdir(), reverse=True):
            if not f.is_file() or not f.suffix == '.db':
                continue
            backups.append({
                "filename": f.name,
                "path": str(f),
                "size_mb": f.stat().st_size / (1024 * 1024),
                "created": datetime.fromtimestamp(f.stat().st_mtime).isoformat(),
                "is_monthly": "monthly" in f.name,
            })
        return backups
