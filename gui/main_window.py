"""Main application window - 9 tab Notebook layout.

Tabs: Dashboard, Sessions, Vacuum, Usage Heatmaps, Session Analytics,
      Diagnostics, Reports, Settings, Help
"""

import tkinter as tk
from tkinter import ttk, filedialog
import logging

logger = logging.getLogger(__name__)


class MainWindow(tk.Tk):
    """Main application window with tabbed interface."""

    def __init__(self, db_manager=None):
        super().__init__()
        self.db = db_manager
        self.title("TESCAN Log Analyzer v2.0")
        self.geometry("1200x800")
        self.minsize(900, 600)

        # Current operator (GLP)
        self.current_user = tk.StringVar(value="")

        self._setup_menu()
        self._setup_operator_bar()
        self._setup_tabs()
        self._setup_statusbar()

        logger.info("Main window initialized")

    def _setup_menu(self):
        """Create application menu bar."""
        menubar = tk.Menu(self)
        self.config(menu=menubar)

        # File menu
        file_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="File", menu=file_menu)
        file_menu.add_command(label="Import Files...", command=self._on_import)
        file_menu.add_command(label="Backup Now", command=self._on_backup)
        file_menu.add_separator()
        file_menu.add_command(label="Exit", command=self.quit)

        # Tools menu
        tools_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="Tools", menu=tools_menu)
        tools_menu.add_command(label="Verify Integrity", command=self._on_verify)

    def _setup_operator_bar(self):
        """Create operator login bar at the top."""
        op_frame = ttk.Frame(self, padding=(10, 5))
        op_frame.pack(fill=tk.X)

        ttk.Label(op_frame, text="Operator:").pack(side=tk.LEFT)
        self.operator_combo = ttk.Combobox(op_frame, textvariable=self.current_user, width=20)
        self.operator_combo.pack(side=tk.LEFT, padx=5)
        self.operator_combo.bind("<<ComboboxSelected>>", self._on_operator_change)

        ttk.Button(op_frame, text="Login", command=self._on_operator_change).pack(side=tk.LEFT, padx=5)

        # Load operator list
        self._refresh_operator_list()

    def _refresh_operator_list(self):
        """Load operators from database."""
        if not self.db:
            self.operator_combo["values"] = ["admin"]
            self.current_user.set("admin")
            return

        try:
            rows = self.db.conn.execute(
                "SELECT username FROM users WHERE active = 1 ORDER BY username"
            ).fetchall()
            users = [r["username"] for r in rows]
            if not users:
                users = ["admin"]
            self.operator_combo["values"] = users
            if not self.current_user.get():
                self.current_user.set(users[0])
        except Exception:
            self.operator_combo["values"] = ["admin"]
            self.current_user.set("admin")

    def _on_operator_change(self, event=None):
        """Handle operator selection change."""
        user = self.current_user.get()
        if user:
            self.status_label.config(text=f"Logged in as: {user}")
            logger.info("Operator changed to: %s", user)

    def _setup_tabs(self):
        """Create the 9-tab notebook with real content."""
        self.notebook = ttk.Notebook(self)
        self.notebook.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        # Import tab modules
        from gui.tabs.tab_dashboard import DashboardTab
        from gui.tabs.tab_sessions import SessionsTab
        from gui.tabs.tab_vacuum import VacuumTab
        from gui.tabs.tab_settings import SettingsTab
        from gui.tabs.tab_reports import ReportsTab
        from gui.tabs.tab_help import HelpTab

        # Dashboard
        self.tab_dashboard = DashboardTab(self.notebook, db_manager=self.db)
        self.notebook.add(self.tab_dashboard, text=" Dashboard ")

        # Sessions
        self.tab_sessions = SessionsTab(self.notebook, db_manager=self.db,
                                         current_user_var=self.current_user)
        self.notebook.add(self.tab_sessions, text=" Sessions ")

        # Vacuum
        self.tab_vacuum = VacuumTab(self.notebook, db_manager=self.db)
        self.notebook.add(self.tab_vacuum, text=" Vacuum ")

        # Usage Heatmaps (placeholder for now - needs matplotlib)
        heatmap_frame = ttk.Frame(self.notebook)
        self.notebook.add(heatmap_frame, text=" Usage Heatmaps ")
        ttk.Label(heatmap_frame, text="Usage Heatmaps",
                  font=("Segoe UI", 14, "bold")).pack(anchor="w", padx=10, pady=10)
        ttk.Label(heatmap_frame, text="Requires matplotlib for rendering.\n"
                  "Select heatmap type, date range, and color scale to generate.").pack(
                      anchor="w", padx=10)

        # Session Analytics (placeholder - needs matplotlib)
        analytics_frame = ttk.Frame(self.notebook)
        self.notebook.add(analytics_frame, text=" Session Analytics ")
        ttk.Label(analytics_frame, text="Session Analytics",
                  font=("Segoe UI", 14, "bold")).pack(anchor="w", padx=10, pady=10)
        ttk.Label(analytics_frame, text="Select a session to view HV/emission charts.\n"
                  "Requires matplotlib (TkAgg backend).").pack(anchor="w", padx=10)

        # Diagnostics (placeholder - needs matplotlib)
        diag_frame = ttk.Frame(self.notebook)
        self.notebook.add(diag_frame, text=" Diagnostics ")
        ttk.Label(diag_frame, text="Diagnostics & Anomalies",
                  font=("Segoe UI", 14, "bold")).pack(anchor="w", padx=10, pady=10)
        ttk.Label(diag_frame, text="Long-term trends, anomaly list, and HV stability.\n"
                  "Requires matplotlib for chart rendering.").pack(anchor="w", padx=10)

        # Reports
        self.tab_reports = ReportsTab(self.notebook, db_manager=self.db,
                                      current_user_var=self.current_user)
        self.notebook.add(self.tab_reports, text=" Reports ")

        # Settings
        self.tab_settings = SettingsTab(self.notebook, db_manager=self.db,
                                        current_user_var=self.current_user)
        self.notebook.add(self.tab_settings, text=" Settings ")

        # Help
        self.tab_help = HelpTab(self.notebook)
        self.notebook.add(self.tab_help, text=" Help ")

    def _setup_statusbar(self):
        """Create status bar at the bottom."""
        self.statusbar = ttk.Frame(self)
        self.statusbar.pack(side=tk.BOTTOM, fill=tk.X)

        self.status_label = ttk.Label(
            self.statusbar, text="Ready", relief=tk.SUNKEN, padding=(5, 2)
        )
        self.status_label.pack(side=tk.LEFT, fill=tk.X, expand=True)

        self.user_label = ttk.Label(
            self.statusbar, textvariable=self.current_user,
            relief=tk.SUNKEN, padding=(5, 2), width=20
        )
        self.user_label.pack(side=tk.RIGHT)

    def _on_import(self):
        """Handle File > Import."""
        directory = filedialog.askdirectory(title="Select log directory")
        if directory:
            self.status_label.config(text=f"Importing from {directory}...")
            logger.info("Import requested: %s", directory)
            # Delegate to dashboard import
            self.tab_dashboard._run_import_folder(directory)
            self.status_label.config(text="Import complete")

    def _on_backup(self):
        """Handle File > Backup."""
        from utils.backup import BackupManager
        mgr = BackupManager()
        path = mgr.create_backup(label="manual")
        self.status_label.config(text=f"Backup saved: {path}")

    def _on_verify(self):
        """Handle Tools > Verify Integrity."""
        if self.db:
            result = self.db.verify_integrity()
            if result["integrity_ok"]:
                self.status_label.config(text="Integrity check: OK")
            else:
                self.status_label.config(
                    text=f"Integrity issues: {len(result['issues'])}"
                )
