"""Dashboard tab - statistics, file import, file removal, recent sessions."""

import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import logging
import os

logger = logging.getLogger(__name__)


class DashboardTab:
    """Dashboard with 9 stat cards, import buttons, file list, recent sessions."""

    def __init__(self, parent, app):
        self.app = app
        self.frame = ttk.Frame(parent, padding=10)
        self._build_ui()
        self.refresh()

    def _build_ui(self):
        """Build dashboard layout."""
        # Stats cards frame (3x3 grid)
        stats_frame = ttk.LabelFrame(self.frame, text="Statistics", padding=10)
        stats_frame.pack(fill=tk.X, pady=(0, 10))

        self.stat_labels = {}
        stat_names = [
            "Total Sessions", "Total Billable Hours", "Total Cost (PLN)",
            "Total Penalties (PLN)", "Imported Files", "HV Samples",
            "Vacuum Cycles", "Anomalies", "Active Users",
        ]
        for i, name in enumerate(stat_names):
            row, col = divmod(i, 3)
            card = ttk.Frame(stats_frame, relief=tk.GROOVE, padding=8)
            card.grid(row=row, column=col, padx=5, pady=5, sticky="nsew")
            ttk.Label(card, text=name, font=("", 9)).pack()
            val_label = ttk.Label(card, text="0", font=("", 14, "bold"))
            val_label.pack()
            self.stat_labels[name] = val_label
            stats_frame.columnconfigure(col, weight=1)

        # Import section
        import_frame = ttk.LabelFrame(self.frame, text="Import Files", padding=10)
        import_frame.pack(fill=tk.X, pady=(0, 10))

        btn_frame = ttk.Frame(import_frame)
        btn_frame.pack(fill=tk.X)
        ttk.Button(btn_frame, text="Add Files...", command=self._add_files).pack(
            side=tk.LEFT, padx=5
        )
        ttk.Button(btn_frame, text="Scan Folder...", command=self._scan_folder).pack(
            side=tk.LEFT, padx=5
        )

        # Imported files list with remove button
        files_frame = ttk.LabelFrame(self.frame, text="Imported Files", padding=5)
        files_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 10))

        cols = ("id", "file_path", "file_type", "import_date", "records")
        self.files_tree = ttk.Treeview(files_frame, columns=cols, show="headings", height=6)
        self.files_tree.heading("id", text="ID")
        self.files_tree.heading("file_path", text="File Path")
        self.files_tree.heading("file_type", text="Type")
        self.files_tree.heading("import_date", text="Import Date")
        self.files_tree.heading("records", text="Records")
        self.files_tree.column("id", width=40)
        self.files_tree.column("file_path", width=400)
        self.files_tree.column("file_type", width=80)
        self.files_tree.column("import_date", width=150)
        self.files_tree.column("records", width=80)

        scrollbar = ttk.Scrollbar(files_frame, orient=tk.VERTICAL, command=self.files_tree.yview)
        self.files_tree.configure(yscrollcommand=scrollbar.set)
        self.files_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        ttk.Button(files_frame, text="REMOVE", command=self._remove_file).pack(
            side=tk.BOTTOM, pady=5
        )
        self.files_tree.bind("<Delete>", lambda e: self._remove_file())

        # Recent sessions
        recent_frame = ttk.LabelFrame(self.frame, text="Recent Sessions (last 10)", padding=5)
        recent_frame.pack(fill=tk.BOTH, expand=True)

        rcols = ("user", "start", "duration", "gvl_time", "status", "cost")
        self.recent_tree = ttk.Treeview(recent_frame, columns=rcols, show="headings", height=5)
        self.recent_tree.heading("user", text="User")
        self.recent_tree.heading("start", text="Start Time")
        self.recent_tree.heading("duration", text="Duration")
        self.recent_tree.heading("gvl_time", text="GVL Time")
        self.recent_tree.heading("status", text="Status")
        self.recent_tree.heading("cost", text="Cost (PLN)")
        for c in rcols:
            self.recent_tree.column(c, width=120)
        self.recent_tree.pack(fill=tk.BOTH, expand=True)

    def refresh(self):
        """Refresh all dashboard data."""
        self._update_stats()
        self._update_files_list()
        self._update_recent_sessions()

    def _update_stats(self):
        """Update statistics cards."""
        try:
            db = self.app.db
            with db.get_cursor() as cursor:
                cursor.execute("SELECT COUNT(*) as cnt FROM sessions")
                total_sessions = cursor.fetchone()["cnt"]

                cursor.execute("SELECT COALESCE(SUM(gvl_total_seconds), 0) as s FROM sessions")
                total_seconds = cursor.fetchone()["s"]
                total_hours = total_seconds / 3600.0

                cursor.execute("SELECT COALESCE(SUM(cost), 0) as c FROM sessions")
                total_cost = cursor.fetchone()["c"]

                cursor.execute("SELECT COALESCE(SUM(amount_pln), 0) as p FROM penalties")
                total_penalties = cursor.fetchone()["p"]

                cursor.execute("SELECT COUNT(*) as cnt FROM file_cache")
                file_count = cursor.fetchone()["cnt"]

                cursor.execute("SELECT COUNT(*) as cnt FROM hv_samples")
                hv_count = cursor.fetchone()["cnt"]

                cursor.execute("SELECT COUNT(*) as cnt FROM vacuum_cycles")
                vac_count = cursor.fetchone()["cnt"]

                cursor.execute("SELECT COUNT(*) as cnt FROM anomalies")
                anom_count = cursor.fetchone()["cnt"]

                cursor.execute("SELECT COUNT(DISTINCT username) as cnt FROM sessions")
                user_count = cursor.fetchone()["cnt"]

            self.stat_labels["Total Sessions"].config(text=str(total_sessions))
            self.stat_labels["Total Billable Hours"].config(text=f"{total_hours:.1f}")
            self.stat_labels["Total Cost (PLN)"].config(text=f"{total_cost:.2f}")
            self.stat_labels["Total Penalties (PLN)"].config(text=f"{total_penalties:.2f}")
            self.stat_labels["Imported Files"].config(text=str(file_count))
            self.stat_labels["HV Samples"].config(text=str(hv_count))
            self.stat_labels["Vacuum Cycles"].config(text=str(vac_count))
            self.stat_labels["Anomalies"].config(text=str(anom_count))
            self.stat_labels["Active Users"].config(text=str(user_count))
        except Exception as e:
            logger.error("Failed to update stats: %s", e)

    def _update_files_list(self):
        """Refresh imported files treeview."""
        for item in self.files_tree.get_children():
            self.files_tree.delete(item)
        try:
            files = self.app.file_repo.get_all()
            for f in files:
                self.files_tree.insert("", tk.END, values=(
                    f["id"],
                    os.path.basename(f["file_path"]),
                    f["file_type"],
                    f.get("import_date", ""),
                    f.get("record_count", 0),
                ))
        except Exception as e:
            logger.error("Failed to load files: %s", e)

    def _update_recent_sessions(self):
        """Refresh recent sessions treeview."""
        for item in self.recent_tree.get_children():
            self.recent_tree.delete(item)
        try:
            sessions = self.app.session_repo.get_all()[:10]
            for s in sessions:
                dur = s.get("duration_seconds", 0)
                dur_str = f"{int(dur // 60)}m {int(dur % 60)}s"
                gvl = s.get("gvl_total_seconds", 0)
                gvl_str = f"{int(gvl // 60)}m {int(gvl % 60)}s"
                self.recent_tree.insert("", tk.END, values=(
                    s.get("username", ""),
                    s.get("start_time", "")[:19] if s.get("start_time") else "",
                    dur_str, gvl_str,
                    s.get("status", ""),
                    f"{s.get('cost', 0):.2f}",
                ))
        except Exception as e:
            logger.error("Failed to load recent sessions: %s", e)

    def _add_files(self):
        """Open file dialog to import log files."""
        filepaths = filedialog.askopenfilenames(
            title="Select Log Files",
            filetypes=[("Log files", "*.log"), ("All files", "*.*")],
        )
        if not filepaths:
            return
        self._do_import(list(filepaths))

    def _scan_folder(self):
        """Open folder dialog for recursive import."""
        folder = filedialog.askdirectory(title="Select Folder to Scan")
        if not folder:
            return
        operator = self.app.get_operator()
        self.app.set_status(f"Scanning folder: {folder}...")
        try:
            results = self.app.import_service.import_folder(folder, operator=operator)
            success = sum(1 for r in results if r.get("status") == "success")
            skipped = sum(1 for r in results if r.get("status") == "skipped")
            errors = sum(1 for r in results if r.get("status") == "error")
            msg = f"Done: {success} imported, {skipped} skipped, {errors} errors"
            self.app.set_status(msg)
            messagebox.showinfo("Import Results", msg)
        except Exception as e:
            messagebox.showerror("Import Error", str(e))
        self.refresh()

    def _do_import(self, filepaths):
        """Import a list of file paths."""
        operator = self.app.get_operator()
        success_count = 0
        for fp in filepaths:
            self.app.set_status(f"Importing: {os.path.basename(fp)}...")
            result = self.app.import_service.import_file(fp, operator=operator)
            if result.get("status") == "success":
                success_count += 1
        self.app.set_status(f"Imported {success_count}/{len(filepaths)} files")
        self.refresh()

    def _remove_file(self):
        """Remove selected imported file and all related data."""
        selected = self.files_tree.selection()
        if not selected:
            messagebox.showwarning("No Selection", "Select a file to remove.")
            return
        item = self.files_tree.item(selected[0])
        file_id = item["values"][0]
        file_name = item["values"][1]

        confirm = messagebox.askyesno(
            "Confirm Deletion",
            f"Remove '{file_name}' and ALL related data?\n"
            "This will delete sessions, vacuum cycles, HV samples, etc.",
        )
        if not confirm:
            return

        operator = self.app.get_operator()
        result = self.app.import_service.delete_file(int(file_id), operator=operator)
        if result.get("status") == "success":
            self.app.set_status(f"Removed: {file_name}")
        else:
            messagebox.showerror("Error", result.get("message", "Unknown error"))
        self.refresh()
