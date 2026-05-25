"""Main application window — 9 tab Notebook layout.

Tabs: Dashboard, Sessions, Vacuum, Heatmaps, Session Analytics,
      Diagnostics, Reports, Settings, Help
"""

import tkinter as tk
from tkinter import ttk
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

    def _setup_tabs(self):
        """Create the 9-tab notebook."""
        self.notebook = ttk.Notebook(self)
        self.notebook.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        # Create placeholder frames for each tab
        tab_names = [
            "Dashboard", "Sessions", "Vacuum", "Heatmaps",
            "Session Analytics", "Diagnostics", "Reports",
            "Settings", "Help"
        ]
        self.tabs = {}
        for name in tab_names:
            frame = ttk.Frame(self.notebook)
            self.notebook.add(frame, text=f" {name} ")
            self.tabs[name] = frame

            # Placeholder label
            ttk.Label(
                frame, text=f"{name} — Tab under construction",
                font=("Segoe UI", 14)
            ).pack(pady=50)

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
        from tkinter import filedialog
        directory = filedialog.askdirectory(title="Select log directory")
        if directory:
            self.status_label.config(text=f"Importing from {directory}...")
            logger.info("Import requested: %s", directory)

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
