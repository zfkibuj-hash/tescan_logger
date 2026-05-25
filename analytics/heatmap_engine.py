"""Heatmap data engine — generates matrices for heatmap visualization.

Supports:
- 6 heatmap types (usage, pumping, penalties, anomalies, idle, gvl)
- Any date range (not limited to single month)
- Hourly / daily / monthly granularity
- Custom color scales with interpolation
"""

import logging
import json
from datetime import datetime, timedelta, date
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass

from models.enums import HeatmapType, HeatmapGranularity

logger = logging.getLogger(__name__)


@dataclass
class ColorPoint:
    """Single point in a custom color scale."""
    value: float  # 0.0 to 1.0 (normalized)
    color: str    # hex color e.g. "#FF0000"


@dataclass
class HeatmapData:
    """Result of heatmap computation."""
    matrix: List[List[float]]  # rows × cols of values
    row_labels: List[str]      # Y-axis labels
    col_labels: List[str]      # X-axis labels
    min_value: float = 0.0
    max_value: float = 0.0
    heatmap_type: HeatmapType = HeatmapType.USAGE_TIME
    granularity: HeatmapGranularity = HeatmapGranularity.DAILY


DEFAULT_COLOR_SCALE = [
    ColorPoint(value=0.0, color="#FFFFFF"),   # No data = white
    ColorPoint(value=0.01, color="#00FF00"),  # Low = green
    ColorPoint(value=0.5, color="#FFFF00"),   # Mid = yellow
    ColorPoint(value=1.0, color="#FF0000"),   # High = red
]



class HeatmapEngine:
    """Generates heatmap data matrices from session/vacuum data.

    Color scale is user-configurable with ≥2 points and linear interpolation.
    """

    def __init__(self, db_manager=None):
        self.db = db_manager
        self.color_scale = DEFAULT_COLOR_SCALE

    def set_color_scale(self, points: List[ColorPoint]) -> None:
        """Set custom color scale (minimum 2 points)."""
        if len(points) < 2:
            raise ValueError("Color scale needs at least 2 points")
        self.color_scale = sorted(points, key=lambda p: p.value)

    def load_color_scale_from_json(self, json_str: str) -> None:
        """Load color scale from JSON settings string."""
        try:
            data = json.loads(json_str)
            points = [ColorPoint(value=p["value"], color=p["color"]) for p in data]
            self.set_color_scale(points)
        except (json.JSONDecodeError, KeyError) as e:
            logger.warning("Invalid color scale JSON, using default: %s", e)
            self.color_scale = DEFAULT_COLOR_SCALE

    def interpolate_color(self, normalized_value: float) -> str:
        """Interpolate color from scale for a normalized value (0-1).

        Uses linear RGB interpolation between color points.
        """
        if normalized_value <= 0:
            return self.color_scale[0].color
        if normalized_value >= 1.0:
            return self.color_scale[-1].color

        # Find surrounding points
        for i in range(len(self.color_scale) - 1):
            low = self.color_scale[i]
            high = self.color_scale[i + 1]
            if low.value <= normalized_value <= high.value:
                # Linear interpolation
                if high.value == low.value:
                    t = 0.0
                else:
                    t = (normalized_value - low.value) / (high.value - low.value)
                return self._lerp_color(low.color, high.color, t)

        return self.color_scale[-1].color

    @staticmethod
    def _lerp_color(color1: str, color2: str, t: float) -> str:
        """Linear interpolation between two hex colors."""
        r1, g1, b1 = HeatmapEngine._hex_to_rgb(color1)
        r2, g2, b2 = HeatmapEngine._hex_to_rgb(color2)
        r = int(r1 + (r2 - r1) * t)
        g = int(g1 + (g2 - g1) * t)
        b = int(b1 + (b2 - b1) * t)
        return f"#{r:02X}{g:02X}{b:02X}"

    @staticmethod
    def _hex_to_rgb(hex_color: str) -> Tuple[int, int, int]:
        """Convert hex color to RGB tuple."""
        hex_color = hex_color.lstrip('#')
        return (
            int(hex_color[0:2], 16),
            int(hex_color[2:4], 16),
            int(hex_color[4:6], 16),
        )


    def generate_usage_heatmap(
        self,
        start_date: date,
        end_date: date,
        granularity: HeatmapGranularity = HeatmapGranularity.DAILY,
        microscope_id: Optional[int] = None,
        username: Optional[str] = None,
    ) -> HeatmapData:
        """Generate usage time heatmap from database.

        Args:
            start_date: Start of range.
            end_date: End of range.
            granularity: hourly/daily/monthly.
            microscope_id: Optional filter.
            username: Optional filter.
        """
        if self.db is None:
            return HeatmapData(matrix=[], row_labels=[], col_labels=[])

        # Build query based on granularity
        if granularity == HeatmapGranularity.DAILY:
            return self._daily_heatmap(
                start_date, end_date, HeatmapType.USAGE_TIME,
                microscope_id, username
            )
        elif granularity == HeatmapGranularity.HOURLY:
            return self._hourly_heatmap(
                start_date, end_date, HeatmapType.USAGE_TIME,
                microscope_id, username
            )
        else:
            return self._monthly_heatmap(
                start_date, end_date, HeatmapType.USAGE_TIME,
                microscope_id, username
            )

    def _daily_heatmap(
        self, start_date: date, end_date: date,
        heatmap_type: HeatmapType,
        microscope_id: Optional[int], username: Optional[str],
    ) -> HeatmapData:
        """Generate daily granularity heatmap (rows=weeks, cols=days)."""
        query = """
            SELECT date(start_time) as day,
                   SUM(duration_seconds) / 3600.0 as hours
            FROM sessions
            WHERE start_time >= ? AND start_time <= ?
              AND cancelled = 0
        """
        params: list = [start_date.isoformat(), end_date.isoformat()]

        if microscope_id:
            query += " AND microscope_id = ?"
            params.append(microscope_id)
        if username:
            query += " AND username = ?"
            params.append(username)

        query += " GROUP BY day ORDER BY day"

        rows = self.db.conn.execute(query, params).fetchall()

        # Build matrix: rows = weeks, cols = Mon-Sun
        day_values: Dict[str, float] = {r["day"]: r["hours"] for r in rows}

        # Generate all days in range
        current = start_date
        all_days = []
        while current <= end_date:
            all_days.append(current)
            current += timedelta(days=1)

        # Group by week
        weeks: List[List[float]] = []
        week_labels: List[str] = []
        current_week: List[float] = []

        for d in all_days:
            if d.weekday() == 0 and current_week:
                weeks.append(current_week)
                current_week = []
            if d.weekday() == 0 or not week_labels:
                week_labels.append(d.strftime("%Y-W%W"))
            current_week.append(day_values.get(d.isoformat(), 0.0))

        if current_week:
            # Pad last week
            while len(current_week) < 7:
                current_week.append(0.0)
            weeks.append(current_week)

        col_labels = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]

        # Pad all weeks to 7 days
        for w in weeks:
            while len(w) < 7:
                w.append(0.0)

        all_values = [v for week in weeks for v in week]
        max_val = max(all_values) if all_values else 0.0

        return HeatmapData(
            matrix=weeks,
            row_labels=week_labels[:len(weeks)],
            col_labels=col_labels,
            min_value=0.0,
            max_value=max_val,
            heatmap_type=heatmap_type,
            granularity=HeatmapGranularity.DAILY,
        )

    def _hourly_heatmap(
        self, start_date: date, end_date: date,
        heatmap_type: HeatmapType,
        microscope_id: Optional[int], username: Optional[str],
    ) -> HeatmapData:
        """Generate hourly heatmap (rows=days, cols=hours 0-23)."""
        query = """
            SELECT date(start_time) as day,
                   CAST(strftime('%H', start_time) AS INTEGER) as hour,
                   SUM(duration_seconds) / 3600.0 as hours
            FROM sessions
            WHERE start_time >= ? AND start_time <= ?
              AND cancelled = 0
        """
        params: list = [start_date.isoformat(), end_date.isoformat()]
        if microscope_id:
            query += " AND microscope_id = ?"
            params.append(microscope_id)
        if username:
            query += " AND username = ?"
            params.append(username)
        query += " GROUP BY day, hour ORDER BY day, hour"

        rows = self.db.conn.execute(query, params).fetchall()

        # Build day→hour→value mapping
        data: Dict[str, Dict[int, float]] = {}
        for r in rows:
            day = r["day"]
            if day not in data:
                data[day] = {}
            data[day][r["hour"]] = r["hours"]

        # Build matrix
        days = sorted(data.keys())
        matrix = []
        for day in days:
            row = [data[day].get(h, 0.0) for h in range(24)]
            matrix.append(row)

        col_labels = [f"{h:02d}" for h in range(24)]
        all_values = [v for row in matrix for v in row]
        max_val = max(all_values) if all_values else 0.0

        return HeatmapData(
            matrix=matrix,
            row_labels=days,
            col_labels=col_labels,
            min_value=0.0,
            max_value=max_val,
            heatmap_type=heatmap_type,
            granularity=HeatmapGranularity.HOURLY,
        )

    def _monthly_heatmap(
        self, start_date: date, end_date: date,
        heatmap_type: HeatmapType,
        microscope_id: Optional[int], username: Optional[str],
    ) -> HeatmapData:
        """Generate monthly heatmap (rows=years, cols=months 1-12)."""
        query = """
            SELECT strftime('%Y', start_time) as year,
                   CAST(strftime('%m', start_time) AS INTEGER) as month,
                   SUM(duration_seconds) / 3600.0 as hours
            FROM sessions
            WHERE start_time >= ? AND start_time <= ?
              AND cancelled = 0
        """
        params: list = [start_date.isoformat(), end_date.isoformat()]
        if microscope_id:
            query += " AND microscope_id = ?"
            params.append(microscope_id)
        if username:
            query += " AND username = ?"
            params.append(username)
        query += " GROUP BY year, month ORDER BY year, month"

        rows = self.db.conn.execute(query, params).fetchall()

        data: Dict[str, Dict[int, float]] = {}
        for r in rows:
            year = r["year"]
            if year not in data:
                data[year] = {}
            data[year][r["month"]] = r["hours"]

        years = sorted(data.keys())
        matrix = []
        for year in years:
            row = [data[year].get(m, 0.0) for m in range(1, 13)]
            matrix.append(row)

        col_labels = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
                      "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
        all_values = [v for row in matrix for v in row]
        max_val = max(all_values) if all_values else 0.0

        return HeatmapData(
            matrix=matrix,
            row_labels=years,
            col_labels=col_labels,
            min_value=0.0,
            max_value=max_val,
            heatmap_type=heatmap_type,
            granularity=HeatmapGranularity.MONTHLY,
        )
