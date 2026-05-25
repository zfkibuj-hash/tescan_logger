"""Dashboard tab - statistics cards, import controls, recent sessions."""

import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import logging
from typing import Optional

logger = logging.getLogger(__name__)


class DashboardTab(ttk.Frame):
    """Dashboard with summary stats, import buttons, recent sessions."""

    def __init__(self, parent, db_manager=None, **kwargs):
        super().__init__(parent, **kwargs)
        self.db = db_manager
        self._build_ui()
        self.refresh()

    def _build_ui(self):
        """Build dashboard layout."""
        # Top section - stats cards
        stats_frame = ttk.LabelFrame(self, text="Summary Statistics", padding=10)
        stats_frame.pack(fill=tk.X, padx=10, pady=(10, 5))

        self.stat_vars = {}
        stat_names = [
            ("Total Sessions", "total_sessions"),
            ("Total Hours", "total_hours"),
            ("Total Cost (PLN)", "total_cost"),
            ("Active Users", "active_users"),
            ("Penalties", "penalties_count"),
            ("Penalties (PLN)", "penalties_total"),
            ("Vacuum Cycles", "vacuum_cycles"),
            ("Anomalies", "anomalies"),
            ("Files Imported", "files_imported"),
        ]

        for i, (label, key) in enumerate(stat_names):
            row, col = divmod(i, 3)
            card = ttk.Frame(stats_frame, relief=tk.RIDGE, borderwidth=1, padding=8)
            card.grid(row=row, column=col, padx=5, pady=3, sticky="ew")
            stats_frame.columnconfigure(col, weight=1)

            ttk.Label(card, text=label, font=("Segoe UI", 9)).pack(anchor="w")
            var = tk.StringVar(value="0")
            self.stat_vars[key] = var
            ttk.Label(card, textvariable=var, font=("Segoe UI", 16, "bold")).pack(anchor="w")

        # Middle section - import controls
        import_frame = ttk.LabelFrame(self, text="Import Log Files", padding=10)
        import_frame.pack(fill=tk.X, padx=10, pady=5)

        btn_frame = ttk.Frame(import_frame)
        btn_frame.pack(fill=tk.X)

        ttk.Button(btn_frame, text="Add Files...", command=self._on_add_files).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="Scan Folder...", command=self._on_scan_folder).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="Refresh Stats", command=self.refresh).pack(side=tk.RIGHT, padx=5)

        self.import_status = tk.StringVar(value="Ready to import")
        ttk.Label(import_frame, textvariable=self.import_status).pack(anchor="w", pady=(5, 0))

        # Bottom section - recent sessions
        recent_frame = ttk.LabelFrame(self, text="Recent Sessions", padding=10)
        recent_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=(5, 10))

        columns = ("user", "start", "duration", "cost", "status", "microscope")
        self.recent_tree = ttk.Treeview(recent_frame, columns=columns, show="headings", height=10)

        self.recent_tree.heading("user", text="User")
        self.recent_tree.heading("start", text="Start Time")
        self.recent_tree.heading("duration", text="Duration (min)")
        self.recent_tree.heading("cost", text="Cost (PLN)")
        self.recent_tree.heading("status", text="Status")
        self.recent_tree.heading("microscope", text="Microscope")

        self.recent_tree.column("user", width=120)
        self.recent_tree.column("start", width=150)
        self.recent_tree.column("duration", width=100)
        self.recent_tree.column("cost", width=100)
        self.recent_tree.column("status", width=120)
        self.recent_tree.column("microscope", width=100)

        scrollbar = ttk.Scrollbar(recent_frame, orient=tk.VERTICAL, command=self.recent_tree.yview)
        self.recent_tree.configure(yscrollcommand=scrollbar.set)

        self.recent_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

    def refresh(self):
        """Refresh dashboard statistics from database."""
        if not self.db:
            return

        try:
            # Session stats
            row = self.db.conn.execute(
                "SELECT COUNT(*), COALESCE(SUM(duration_seconds)/3600.0, 0), "
                "COALESCE(SUM(calculated_cost), 0) FROM sessions WHERE cancelled = 0"
            ).fetchone()
            self.stat_vars["total_sessions"].set(str(row[0]))
            self.stat_vars["total_hours"].set(f"{row[1]:.1f}")
            self.stat_vars["total_cost"].set(f"{row[2]:.2f}")

            # Users
            row = self.db.conn.execute(
                "SELECT COUNT(DISTINCT username) FROM sessions"
            ).fetchone()
            self.stat_vars["active_users"].set(str(row[0]))

            # Penalties
            row = self.db.conn.execute(
                "SELECT COUNT(*), COALESCE(SUM(amount), 0) FROM penalties"
            ).fetchone()
            self.stat_vars["penalties_count"].set(str(row[0]))
            self.stat_vars["penalties_total"].set(f"{row[1]:.0f}")

            # Vacuum
            row = self.db.conn.execute("SELECT COUNT(*) FROM vacuum_cycles").fetchone()
            self.stat_vars["vacuum_cycles"].set(str(row[0]))

            # Anomalies
            row = self.db.conn.execute("SELECT COUNT(*) FROM anomalies").fetchone()
            self.stat_vars["anomalies"].set(str(row[0]))

            # Files
            row = self.db.conn.execute("SELECT COUNT(*) FROM file_cache").fetchone()
            self.stat_vars["files_imported"].set(str(row[0]))

            # Recent sessions
            self._load_recent_sessions()

        except Exception as e:
            logger.error("Error refreshing dashboard: %s", e)

    def _load_recent_sessions(self):
        """Load last 20 sessions into treeview."""
        for item in self.recent_tree.get_children():
            self.recent_tree.delete(item)

        if not self.db:
            return

        rows = self.db.conn.execute(
            """SELECT username, start_time, duration_seconds, calculated_cost,
                      status, microscope_type
               FROM sessions ORDER BY start_time DESC LIMIT 20"""
        ).fetchall()

        for row in rows:
            start = row["start_time"][:16] if row["start_time"] else ""
            duration = f"{(row['duration_seconds'] or 0) / 60:.1f}"
            cost = f"{row['calculated_cost'] or 0:.2f}"
            self.recent_tree.insert("", tk.END, values=(
                row["username"], start, duration, cost,
                row["status"], row["microscope_type"]
            ))

    def _on_add_files(self):
        """Handle Add Files button."""
        files = filedialog.askopenfilenames(
            title="Select log files",
            filetypes=[("Log files", "*.log"), ("All files", "*.*")]
        )
        if files:
            self.import_status.set(f"Selected {len(files)} files - importing...")
            self.update_idletasks()
            self._run_import(list(files))

    def _on_scan_folder(self):
        """Handle Scan Folder button."""
        directory = filedialog.askdirectory(title="Select log directory")
        if directory:
            self.import_status.set(f"Scanning {directory}...")
            self.update_idletasks()
            self._run_import_folder(directory)

    def _run_import(self, file_paths):
        """Run import on selected files."""
        try:
            from parser.file_registry import FileRegistry
            from services.import_service import ImportService
            from models.enums import MicroscopeType

            registry = FileRegistry()
            typed_files = registry.filter_files(file_paths)

            service = ImportService(db_manager=self.db, microscope_id=1)
            result = service.import_files(typed_files)

            self.import_status.set(
                f"Done: {result.files_processed} files, "
                f"{result.sessions_created} sessions, "
                f"{result.hv_samples_imported} HV samples"
            )
            self.refresh()

        except Exception as e:
            self.import_status.set(f"Error: {e}")
            logger.error("Import error: %s", e)

    def _run_import_folder(self, directory):
        """Run import on folder."""
        try:
            from parser.file_registry import FileRegistry
            from services.import_service import ImportService

            registry = FileRegistry()
            files = registry.scan_directory(directory)

            service = ImportService(db_manager=self.db, microscope_id=1)
            result = service.import_files(files)

            self.import_status.set(
                f"Done: {result.files_processed} files, "
                f"{result.sessions_created} sessions, "
                f"{result.hv_samples_imported} HV samples"
            )
            self.refresh()

        except Exception as e:
            self.import_status.set(f"Error: {e}")
            logger.error("Import error: %s", e)
