"""Import service - orchestrates the full import pipeline.

Pipeline: scan files -> check cache -> parse -> build sessions ->
analyze vacuum -> calculate costs -> persist to DB.
"""

import logging
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass

from models.enums import FileType, MicroscopeType
from models.dataclasses import Session, VacuumCycle, Penalty
from parser.log_parser import HistoryLogParser
from parser.hv_parser import HVLogParser
from parser.file_registry import FileRegistry
from services.session_builder import SessionBuilder
from services.vacuum_analyzer import VacuumAnalyzer
from services.billing_service import BillingService

logger = logging.getLogger(__name__)



@dataclass
class ImportResult:
    """Result of an import operation."""
    files_processed: int = 0
    files_skipped: int = 0
    sessions_created: int = 0
    vacuum_cycles_created: int = 0
    penalties_created: int = 0
    hv_samples_imported: int = 0
    errors: List[dict] = None

    def __post_init__(self):
        if self.errors is None:
            self.errors = []


class ImportService:
    """Orchestrates the full import pipeline.

    Steps:
    1. Scan/filter files
    2. Check file_cache (skip already imported)
    3. Parse History files -> events
    4. Build sessions from events
    5. Analyze vacuum cycles
    6. Calculate billing costs
    7. Persist everything to database
    """

    def __init__(self, db_manager=None, microscope_id: int = 0,
                 microscope_type: MicroscopeType = MicroscopeType.VEGA3):
        self.db = db_manager
        self.microscope_id = microscope_id
        self.microscope_type = microscope_type
        self.file_registry = FileRegistry()
        self.history_parser = HistoryLogParser()
        self.hv_parser = HVLogParser()
        self.session_builder = SessionBuilder(microscope_type, microscope_id)
        self.vacuum_analyzer = VacuumAnalyzer(microscope_id)
        self.billing_service = BillingService()


    def is_file_cached(self, file_path: str) -> bool:
        """Check if file was already imported (by hash)."""
        if self.db is None:
            return False
        file_hash = FileRegistry.compute_file_hash(file_path)
        row = self.db.conn.execute(
            "SELECT id FROM file_cache WHERE file_hash = ?",
            (file_hash,)
        ).fetchone()
        return row is not None

    def cache_file(self, file_path: str, file_type: str,
                   record_count: int) -> None:
        """Mark file as imported in cache."""
        if self.db is None:
            return
        import os
        file_hash = FileRegistry.compute_file_hash(file_path)
        file_size = os.path.getsize(file_path)
        self.db.conn.execute(
            """INSERT OR REPLACE INTO file_cache
               (file_path, file_hash, file_size, file_type, record_count)
               VALUES (?, ?, ?, ?, ?)""",
            (file_path, file_hash, file_size, file_type, record_count)
        )
        self.db.conn.commit()


    def import_history_file(self, file_path: str) -> Tuple[
        List[Session], List[VacuumCycle], List[Penalty]
    ]:
        """Import a single History log file.

        Returns:
            Tuple of (sessions, vacuum_cycles, penalties).
        """
        # Parse events
        events = self.history_parser.parse_file(file_path)
        if not events:
            return [], [], []

        # Auto-detect microscope type if needed
        detected_type = self.history_parser.detect_microscope_type(events)
        if detected_type != self.microscope_type:
            logger.info(
                "Detected type %s differs from configured %s for %s",
                detected_type.value, self.microscope_type.value, file_path
            )

        # Build sessions
        builder = SessionBuilder(detected_type, self.microscope_id)
        sessions = builder.build_sessions(events, file_path)

        # Analyze vacuum
        cycles, penalties, anomalies = self.vacuum_analyzer.analyze(events, file_path)

        # Calculate costs
        self.billing_service.calculate_batch(sessions)

        return sessions, cycles, penalties


    def import_files(self, file_paths: List[Tuple[str, FileType]]) -> ImportResult:
        """Import multiple files (History and/or HV).

        Args:
            file_paths: List of (path, FileType) tuples.

        Returns:
            ImportResult with counts and errors.
        """
        result = ImportResult()

        for file_path, file_type in file_paths:
            # Skip cached files
            if self.is_file_cached(file_path):
                result.files_skipped += 1
                continue

            try:
                if file_type == FileType.HISTORY:
                    sessions, cycles, penalties = self.import_history_file(
                        file_path
                    )
                    result.sessions_created += len(sessions)
                    result.vacuum_cycles_created += len(cycles)
                    result.penalties_created += len(penalties)

                    # Persist if DB available
                    if self.db:
                        self._persist_sessions(sessions)
                        self._persist_vacuum(cycles, penalties)
                        record_count = len(sessions) + len(cycles)
                        self.cache_file(
                            file_path, "HISTORY", record_count
                        )

                elif file_type == FileType.HV:
                    count = self._import_hv_file(file_path)
                    result.hv_samples_imported += count
                    if self.db:
                        self.cache_file(file_path, "HV", count)

                result.files_processed += 1

            except Exception as e:
                logger.error("Error importing %s: %s", file_path, e)
                result.errors.append({
                    "file_path": file_path,
                    "error": str(e),
                })

        # Collect parser errors
        result.errors.extend(self.history_parser.get_errors())
        result.errors.extend(self.hv_parser.get_errors())

        logger.info(
            "Import complete: %d processed, %d skipped, %d sessions",
            result.files_processed, result.files_skipped,
            result.sessions_created
        )
        return result


    def _import_hv_file(self, file_path: str) -> int:
        """Import HV log file into HV database.

        Returns number of samples imported.
        """
        if self.db is None:
            return 0

        count = 0
        batch = []
        BATCH_SIZE = 1000

        for sample in self.hv_parser.parse_file_generator(
            file_path, self.microscope_id
        ):
            batch.append((
                sample.microscope_id,
                sample.timestamp.isoformat() if sample.timestamp else None,
                file_path,
                sample.set_hv_kv,
                sample.actual_hv_kv,
                sample.emission_current_ua,
                sample.filament_current_a,
                sample.gun_pressure_pa,
                sample.chamber_pressure_pa,
                sample.heating_percent,
                sample.gun_valve_state,
                sample.extractor_voltage_kv,
                sample.suppressor_voltage_v,
                sample.total_current_ua,
                sample.flags_hex,
                sample.column_ion_pump_pressure_pa,
            ))
            count += 1

            if len(batch) >= BATCH_SIZE:
                self._insert_hv_batch(batch)
                batch.clear()

        if batch:
            self._insert_hv_batch(batch)

        self.db.hv_conn.commit()
        logger.info("Imported %d HV samples from %s", count, file_path)
        return count

    def _insert_hv_batch(self, batch: list) -> None:
        """Insert batch of HV samples into HV database."""
        self.db.hv_conn.executemany(
            """INSERT INTO hv_samples
               (microscope_id, timestamp, source_file,
                set_hv_kv, actual_hv_kv, emission_current_ua,
                filament_current_a, gun_pressure_pa, chamber_pressure_pa,
                heating_percent, gun_valve_state, extractor_voltage_kv,
                suppressor_voltage_v, total_current_ua, flags_hex,
                column_ion_pump_pressure_pa)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            batch
        )


    def _persist_sessions(self, sessions: List[Session]) -> None:
        """Persist sessions to main database."""
        for session in sessions:
            cursor = self.db.conn.execute(
                """INSERT INTO sessions
                   (microscope_id, microscope_type, username,
                    start_time, end_time, duration_seconds, status,
                    billing_tier, hourly_rate, discount_percent,
                    calculated_cost, hv_on_time, hv_off_time,
                    gvl_open_time, gvl_close_time, source_file)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    session.microscope_id,
                    session.microscope_type.value,
                    session.username,
                    session.start_time.isoformat() if session.start_time else None,
                    session.end_time.isoformat() if session.end_time else None,
                    session.duration_seconds,
                    session.status.value,
                    session.billing_tier.value,
                    session.hourly_rate,
                    session.discount_percent,
                    session.calculated_cost,
                    session.hv_on_time.isoformat() if session.hv_on_time else None,
                    session.hv_off_time.isoformat() if session.hv_off_time else None,
                    session.gvl_open_time.isoformat() if session.gvl_open_time else None,
                    session.gvl_close_time.isoformat() if session.gvl_close_time else None,
                    session.source_file,
                )
            )
            session.id = cursor.lastrowid
        self.db.conn.commit()

    def _persist_vacuum(self, cycles: List[VacuumCycle],
                        penalties: List[Penalty]) -> None:
        """Persist vacuum cycles and penalties to main database."""
        for cycle in cycles:
            cursor = self.db.conn.execute(
                """INSERT INTO vacuum_cycles
                   (microscope_id, session_id, username, command,
                    start_time, end_time, duration_seconds,
                    status, ready_time_seconds, source_file)
                   VALUES (?,?,?,?,?,?,?,?,?,?)""",
                (
                    cycle.microscope_id,
                    cycle.session_id,
                    cycle.username,
                    cycle.command,
                    cycle.start_time.isoformat() if cycle.start_time else None,
                    cycle.end_time.isoformat() if cycle.end_time else None,
                    cycle.duration_seconds,
                    cycle.status.value,
                    cycle.ready_time_seconds,
                    cycle.source_file,
                )
            )
            cycle.id = cursor.lastrowid

        for penalty in penalties:
            self.db.conn.execute(
                """INSERT INTO penalties
                   (vacuum_cycle_id, microscope_id, username,
                    amount, reason, timestamp)
                   VALUES (?,?,?,?,?,?)""",
                (
                    penalty.vacuum_cycle_id,
                    penalty.microscope_id,
                    penalty.username,
                    penalty.amount,
                    penalty.reason,
                    penalty.timestamp.isoformat() if penalty.timestamp else None,
                )
            )
        self.db.conn.commit()
