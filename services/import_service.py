"""Import service - file import pipeline and deletion.

Handles: import of history/HV files, incremental import (hash dedup),
file deletion (removes ALL related data), audit logging.
"""

import hashlib
import os
import logging
import re
from typing import List, Optional

from database.db_manager import DatabaseManager
from parser.log_parser import HistoryLogParser
from parser.hv_parser import HVLogParser
from services.session_builder import SessionBuilder
from services.vacuum_analyzer import VacuumAnalyzer
from services.billing_service import BillingService
from models.enums import FileType, AuditAction

logger = logging.getLogger(__name__)

HISTORY_PATTERN = re.compile(r"[Hh]istory.*\.log$", re.IGNORECASE)
HV_PATTERN = re.compile(r"hv.*\.log$", re.IGNORECASE)


class ImportService:
    """Manages file import pipeline and deletion."""

    def __init__(self, db: DatabaseManager):
        self.db = db
        self.history_parser = HistoryLogParser()
        self.hv_parser = HVLogParser()
        self.session_builder = SessionBuilder()

    def detect_file_type(self, file_path: str) -> Optional[FileType]:
        """Auto-detect file type from filename."""
        basename = os.path.basename(file_path)
        if HISTORY_PATTERN.search(basename):
            return FileType.HISTORY
        if HV_PATTERN.search(basename):
            return FileType.HV
        return None

    def compute_file_hash(self, file_path: str) -> str:
        """Compute SHA-256 hash of file content."""
        hasher = hashlib.sha256()
        try:
            with open(file_path, "rb") as f:
                while True:
                    chunk = f.read(65536)
                    if not chunk:
                        break
                    hasher.update(chunk)
        except OSError as e:
            logger.error("Failed to hash file %s: %s", file_path, e)
            return ""
        return hasher.hexdigest()

    def is_already_imported(self, file_hash: str) -> bool:
        """Check if file with given hash was already imported."""
        with self.db.get_cursor() as cursor:
            cursor.execute("SELECT id FROM file_cache WHERE file_hash = ?", (file_hash,))
            return cursor.fetchone() is not None

    def import_file(self, file_path: str, operator: str = "system") -> dict:
        """Import a single file (history or HV). Returns dict with status/message."""
        file_type = self.detect_file_type(file_path)
        if file_type is None:
            return {"status": "error", "message": f"Cannot detect file type: {file_path}", "record_count": 0}
        if not os.path.isfile(file_path):
            return {"status": "error", "message": f"File not found: {file_path}", "record_count": 0}
        file_hash = self.compute_file_hash(file_path)
        if not file_hash:
            return {"status": "error", "message": "Failed to compute file hash", "record_count": 0}
        if self.is_already_imported(file_hash):
            return {"status": "skipped", "message": "File already imported (hash match)", "record_count": 0}
        if file_type == FileType.HISTORY:
            return self._import_history(file_path, file_hash, operator)
        return self._import_hv(file_path, file_hash, operator)

    def _import_history(self, file_path: str, file_hash: str, operator: str) -> dict:
        """Import a history log file."""
        events = self.history_parser.parse_file(file_path)
        if not events:
            return {"status": "error", "message": "No events parsed from file", "record_count": 0}
        sessions = self.session_builder.build_sessions(events, file_path)
        # Vacuum analysis
        pump_warn = float(self.db.get_setting("pump_time_warning_seconds", "300"))
        pump_crit = float(self.db.get_setting("pump_time_critical_seconds", "600"))
        idle_thresh = float(self.db.get_setting("idle_after_ready_threshold_seconds", "1800"))
        vacuum_analyzer = VacuumAnalyzer(pump_warn, pump_crit, idle_thresh)
        vacuum_result = vacuum_analyzer.analyze_events(events, source_file=file_path)
        # Cost calculation
        rate = float(self.db.get_setting("rate_pln_per_hour", "150.0"))
        billing = BillingService(rate_pln_per_hour=rate)
        for session in sessions:
            session.cost = billing.calculate_session_cost(session)
        # Store data
        record_count = self._store_history_data(file_path, file_hash, sessions, vacuum_result, operator)
        return {
            "status": "success",
            "message": f"Imported {len(sessions)} sessions, {len(vacuum_result['cycles'])} vacuum cycles",
            "record_count": record_count,
            "sessions": len(sessions),
            "vacuum_cycles": len(vacuum_result["cycles"]),
            "penalties": len(vacuum_result["penalties"]),
            "anomalies": len(vacuum_result["anomalies"]),
        }

    def _store_history_data(self, file_path, file_hash, sessions, vacuum_result, operator):
        """Store parsed history data in database."""
        record_count = 0
        with self.db.get_cursor() as cursor:
            for s in sessions:
                cursor.execute(
                    """INSERT INTO sessions (username, start_time, end_time, duration_seconds,
                     gvl_total_seconds, gvl_cycle_count, status, cost, discount_percent,
                     source_file, notes) VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                    (s.username, s.start_time.isoformat() if s.start_time else None,
                     s.end_time.isoformat() if s.end_time else None, s.duration_seconds,
                     s.gvl_total_seconds, len(s.gvl_cycles), s.status.value, s.cost,
                     s.discount_percent, file_path, s.notes))
                record_count += 1
            for c in vacuum_result["cycles"]:
                cursor.execute(
                    """INSERT INTO vacuum_cycles (session_id, pump_start, ready_time, end_time,
                     status, pump_duration_seconds, source_file) VALUES (?,?,?,?,?,?,?)""",
                    (c.session_id, c.pump_start.isoformat() if c.pump_start else None,
                     c.ready_time.isoformat() if c.ready_time else None,
                     c.end_time.isoformat() if c.end_time else None,
                     c.status.value, c.pump_duration_seconds, file_path))
                record_count += 1
            for p in vacuum_result["penalties"]:
                cursor.execute(
                    """INSERT INTO penalties (session_id, vacuum_cycle_id, penalty_type,
                     amount_pln, username, timestamp, source_file, notes) VALUES (?,?,?,?,?,?,?,?)""",
                    (p.session_id, p.vacuum_cycle_id, p.penalty_type, p.amount_pln,
                     p.username, p.timestamp.isoformat() if p.timestamp else None, file_path, p.notes))
                record_count += 1
            for a in vacuum_result["anomalies"]:
                cursor.execute(
                    """INSERT INTO anomalies (anomaly_type, session_id, timestamp,
                     duration_seconds, severity, description, source_file) VALUES (?,?,?,?,?,?,?)""",
                    (a.anomaly_type.value, a.session_id,
                     a.timestamp.isoformat() if a.timestamp else None,
                     a.duration_seconds, a.severity, a.description, file_path))
                record_count += 1
            for err in self.history_parser.errors:
                cursor.execute(
                    "INSERT INTO parser_errors (source_file, line_number, raw_line, error_message) VALUES (?,?,?,?)",
                    (err["source_file"], err["line_number"], err["raw_line"], err["error_message"]))
            cursor.execute(
                "INSERT INTO file_cache (file_path, file_hash, file_type, record_count) VALUES (?,?,?,?)",
                (file_path, file_hash, FileType.HISTORY.value, record_count))
            cursor.execute(
                "INSERT INTO audit_log (action, entity_type, changed_by, new_value) VALUES (?,?,?,?)",
                (AuditAction.IMPORT.value, "file", operator, f"{file_path} ({record_count} records)"))
        return record_count

    def _import_hv(self, file_path: str, file_hash: str, operator: str) -> dict:
        """Import an HV data log file."""
        record_count = 0
        with self.db.get_cursor() as cursor:
            for batch in self.hv_parser.parse_file_batches(file_path):
                for sample in batch:
                    cursor.execute(
                        """INSERT INTO hv_samples (timestamp, set_hv_kv, actual_hv_kv,
                         emission_current_ua, emitter_current_a, heating_percent,
                         gun_pressure_pa, chamber_pressure_pa, gun_valve_state, source_file)
                         VALUES (?,?,?,?,?,?,?,?,?,?)""",
                        (sample.timestamp.isoformat() if sample.timestamp else None,
                         sample.set_hv_kv, sample.actual_hv_kv, sample.emission_current_ua,
                         sample.emitter_current_a, sample.heating_percent, sample.gun_pressure_pa,
                         sample.chamber_pressure_pa, sample.gun_valve_state, file_path))
                    record_count += 1
            cursor.execute(
                "INSERT INTO file_cache (file_path, file_hash, file_type, record_count) VALUES (?,?,?,?)",
                (file_path, file_hash, FileType.HV.value, record_count))
            for err in self.hv_parser.errors:
                cursor.execute(
                    "INSERT INTO parser_errors (source_file, line_number, raw_line, error_message) VALUES (?,?,?,?)",
                    (err["source_file"], err["line_number"], err["raw_line"], err["error_message"]))
            cursor.execute(
                "INSERT INTO audit_log (action, entity_type, changed_by, new_value) VALUES (?,?,?,?)",
                (AuditAction.IMPORT.value, "file", operator, f"{file_path} ({record_count} HV samples)"))
        return {"status": "success", "message": f"Imported {record_count} HV samples", "record_count": record_count}

    def delete_file(self, file_id: int, operator: str = "system") -> dict:
        """Delete an imported file and ALL related data."""
        with self.db.get_cursor() as cursor:
            cursor.execute("SELECT * FROM file_cache WHERE id = ?", (file_id,))
            file_record = cursor.fetchone()
            if file_record is None:
                return {"status": "error", "message": "File not found"}
            file_path = file_record["file_path"]
            deleted_counts = {}
            tables = ["sessions", "vacuum_cycles", "hv_samples", "anomalies", "penalties", "parser_errors"]
            for table in tables:
                cursor.execute(f"SELECT COUNT(*) as cnt FROM {table} WHERE source_file = ?", (file_path,))
                count = cursor.fetchone()["cnt"]
                cursor.execute(f"DELETE FROM {table} WHERE source_file = ?", (file_path,))
                deleted_counts[table] = count
            cursor.execute("DELETE FROM file_cache WHERE id = ?", (file_id,))
            total_deleted = sum(deleted_counts.values())
            cursor.execute(
                """INSERT INTO audit_log (action, entity_type, entity_id, changed_by, old_value, new_value)
                VALUES (?,?,?,?,?,?)""",
                (AuditAction.DELETE_FILE.value, "file", file_id, operator,
                 file_path, f"Deleted {total_deleted} records: {deleted_counts}"))
        logger.info("Deleted file %s (ID %d): %s", file_path, file_id, deleted_counts)
        return {"status": "success", "message": f"Deleted file and {total_deleted} related records",
                "deleted_counts": deleted_counts}

    def import_folder(self, folder_path: str, operator: str = "system") -> List[dict]:
        """Recursively scan folder and import all log files."""
        results = []
        if not os.path.isdir(folder_path):
            return [{"status": "error", "message": f"Not a directory: {folder_path}"}]
        for root, _dirs, files in os.walk(folder_path):
            for filename in sorted(files):
                if not filename.endswith(".log"):
                    continue
                full_path = os.path.join(root, filename)
                if self.detect_file_type(full_path) is not None:
                    result = self.import_file(full_path, operator)
                    result["file"] = full_path
                    results.append(result)
        return results
