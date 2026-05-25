"""HV samples repository — accesses the separate HV database.

Provides query methods with SQL-side downsampling for performance.
"""

import logging
from datetime import datetime
from typing import List, Optional

from models.hv_models import HVSample

logger = logging.getLogger(__name__)


class HVRepository:
    """Repository for HV sample data (separate database)."""

    def __init__(self, db_manager):
        self.db = db_manager

    def get_samples(
        self,
        microscope_id: int,
        start_time: Optional[str] = None,
        end_time: Optional[str] = None,
        downsample: int = 1,
        limit: int = 10000,
    ) -> List[HVSample]:
        """Get HV samples with SQL-side downsampling.

        Args:
            microscope_id: Filter by microscope.
            start_time: ISO format start time.
            end_time: ISO format end time.
            downsample: Take every Nth row (1=all, 5=every 5th).
            limit: Maximum rows to return.
        """
        query = "SELECT * FROM hv_samples WHERE microscope_id = ?"
        params: list = [microscope_id]

        if start_time:
            query += " AND timestamp >= ?"
            params.append(start_time)
        if end_time:
            query += " AND timestamp <= ?"
            params.append(end_time)

        if downsample > 1:
            query += f" AND (rowid % {downsample}) = 0"

        query += " ORDER BY timestamp LIMIT ?"
        params.append(limit)

        rows = self.db.hv_conn.execute(query, params).fetchall()
        return [self._row_to_sample(r) for r in rows]


    def get_sample_count(
        self, microscope_id: int,
        start_time: Optional[str] = None,
        end_time: Optional[str] = None,
    ) -> int:
        """Get count of HV samples in range."""
        query = "SELECT COUNT(*) FROM hv_samples WHERE microscope_id = ?"
        params: list = [microscope_id]
        if start_time:
            query += " AND timestamp >= ?"
            params.append(start_time)
        if end_time:
            query += " AND timestamp <= ?"
            params.append(end_time)
        row = self.db.hv_conn.execute(query, params).fetchone()
        return row[0] if row else 0

    def get_auto_downsample(
        self, microscope_id: int,
        start_time: Optional[str] = None,
        end_time: Optional[str] = None,
        target_points: int = 5000,
    ) -> int:
        """Calculate optimal downsample factor for target display points."""
        count = self.get_sample_count(microscope_id, start_time, end_time)
        if count <= target_points:
            return 1
        return max(1, count // target_points)

    def _row_to_sample(self, row) -> HVSample:
        return HVSample(
            id=row["id"],
            microscope_id=row["microscope_id"],
            timestamp=datetime.fromisoformat(row["timestamp"]) if row["timestamp"] else None,
            source_file=row["source_file"] or "",
            set_hv_kv=row["set_hv_kv"] or 0.0,
            actual_hv_kv=row["actual_hv_kv"] or 0.0,
            emission_current_ua=row["emission_current_ua"] or 0.0,
            filament_current_a=row["filament_current_a"] or 0.0,
            gun_pressure_pa=row["gun_pressure_pa"] or 0.0,
            chamber_pressure_pa=row["chamber_pressure_pa"] or 0.0,
            heating_percent=row["heating_percent"],
            gun_valve_state=row["gun_valve_state"],
            extractor_voltage_kv=row["extractor_voltage_kv"],
            suppressor_voltage_v=row["suppressor_voltage_v"],
            total_current_ua=row["total_current_ua"],
            flags_hex=row["flags_hex"],
            column_ion_pump_pressure_pa=row["column_ion_pump_pressure_pa"],
        )
