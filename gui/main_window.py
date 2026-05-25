"""Main application window with 7 tabs, operator selector, and status bar."""

import tkinter as tk
from tkinter import ttk
import logging
import os
import sys

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from database.db_manager import DatabaseManager
from repositories.repositories import (
    SessionRepository,
    VacuumRepository,
    UserRepository,
    AuditRepository,
    HVRepository,
    FileRepository,
    SettingsRepository,
    PenaltyRepository,
    AnomalyRepository,
)
from services.import_service import ImportService
from services.billing_service import BillingService

logger = logging.getLogger(__name__)


class MainWindow:
    """Main application window with notebook tabs and operator dropdown."""

    def __init__(self, db: DatabaseManager):
        self.db = db
        self.root = tk.Tk()
        self.root.title("TESCAN VEGA3 Log Analyzer")
        self.root.geometry("1280x800")
        self.root.minsize(1024, 600)

        # Repositories
        self.session_repo = SessionRepository(db)
        self.vacuum_repo = VacuumRepository(db)
        self.user_repo = UserRepository(db)
        self.audit_repo = AuditRepository(db)
        self.hv_repo = HVRepository(db)
        self.file_repo = FileRepository(db)
        self.settings_repo = SettingsRepository(db)
        self.penalty_repo = PenaltyRepository(db)
        self.anomaly_repo = AnomalyRepository(db)

        # Services
        self.import_service = ImportService(db)
        rate = float(self.settings_repo.get("rate_pln_per_hour", "150.0"))
        self.billing_service = BillingService(rate_pln_per_hour=rate)

        # Current operator
        self.current_operator = tk.StringVar(value="admin")

        self._build_ui()

    def _build_ui(self):
        """Build the main UI layout."""
        # Top bar with operator selector
        top_frame = ttk.Frame(self.root, padding=5)
        top_frame.pack(fill=tk.X, side=tk.TOP)

        ttk.Label(top_frame, text="Operator:").pack(side=tk.LEFT, padx=(0, 5))
        self.operator_combo = ttk.Combobox(
            top_frame, textvariable=self.current_operator, width=20, state="readonly"
        )
        self.operator_combo.pack(side=tk.LEFT)
        self._refresh_operators()

        ttk.Button(top_frame, text="Refresh", command=self._refresh_all).pack(
            side=tk.RIGHT, padx=5
        )

        # Notebook with 7 tabs
        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        self._create_tabs()

        # Status bar
        self.status_var = tk.StringVar(value="Ready")
        status_bar = ttk.Label(
            self.root, textvariable=self.status_var, relief=tk.SUNKEN, anchor=tk.W
        )
        status_bar.pack(fill=tk.X, side=tk.BOTTOM, padx=2, pady=2)

    def _create_tabs(self):
        """Create all 7 tabs in the notebook."""
        from gui.tabs.tab_dashboard import DashboardTab
        from gui.tabs.tab_sessions import SessionsTab
        from gui.tabs.tab_vacuum import VacuumTab
        from gui.tabs.tab_heatmaps import HeatmapsTab
        from gui.tabs.tab_hv_charts import HVChartsTab
        from gui.tabs.tab_settings import SettingsTab
        from gui.tabs.tab_help import HelpTab

        self.tab_dashboard = DashboardTab(self.notebook, self)
        self.notebook.add(self.tab_dashboard.frame, text="Dashboard")

        self.tab_sessions = SessionsTab(self.notebook, self)
        self.notebook.add(self.tab_sessions.frame, text="Sessions")

        self.tab_vacuum = VacuumTab(self.notebook, self)
        self.notebook.add(self.tab_vacuum.frame, text="Vacuum")

        self.tab_heatmaps = HeatmapsTab(self.notebook, self)
        self.notebook.add(self.tab_heatmaps.frame, text="Usage Heatmaps")

        self.tab_hv_charts = HVChartsTab(self.notebook, self)
        self.notebook.add(self.tab_hv_charts.frame, text="HV Charts")

        self.tab_settings = SettingsTab(self.notebook, self)
        self.notebook.add(self.tab_settings.frame, text="Settings")

        self.tab_help = HelpTab(self.notebook, self)
        self.notebook.add(self.tab_help.frame, text="Help")

    def _refresh_operators(self):
        """Refresh operator dropdown from users table."""
        users = self.user_repo.get_all()
        names = [u["username"] for u in users]
        if "admin" not in names:
            names.insert(0, "admin")
        self.operator_combo["values"] = names
        if self.current_operator.get() not in names:
            self.current_operator.set(names[0] if names else "admin")

    def _refresh_all(self):
        """Refresh all tabs data."""
        self._refresh_operators()
        self.tab_dashboard.refresh()
        self.tab_sessions.refresh()
        self.tab_vacuum.refresh()
        self.set_status("Data refreshed")

    def set_status(self, message: str):
        """Update status bar text."""
        self.status_var.set(message)
        self.root.update_idletasks()

    def get_operator(self) -> str:
        """Get current operator name."""
        return self.current_operator.get()

    def run(self):
        """Start the main event loop."""
        self.root.mainloop()


def launch_gui(db: DatabaseManager):
    """Launch the main GUI window."""
    app = MainWindow(db)
    app.run()
