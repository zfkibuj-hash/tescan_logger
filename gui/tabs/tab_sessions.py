"""Sessions tab - list with filters and right-click (PPM) context menu."""

import tkinter as tk
from tkinter import ttk, simpledialog, messagebox
import logging

logger = logging.getLogger(__name__)


class SessionsTab(ttk.Frame):
    """Sessions list with filters, sorting, and PPM context menu."""

    def __init__(self, parent, db_manager=None, current_user_var=None, **kwargs):
        super().__init__(parent, **kwargs)
        self.db = db_manager
        self.current_user_var = current_user_var or tk.StringVar(value="admin")
        self._build_ui()
        self.refresh()

    def _build_ui(self):
        """Build sessions tab layout."""
        # Filter bar
        filter_frame = ttk.Frame(self, padding=5)
        filter_frame.pack(fill=tk.X, padx=10, pady=(10, 0))

        ttk.Label(filter_frame, text="User:").pack(side=tk.LEFT)
        self.filter_user = ttk.Combobox(filter_frame, width=15, values=["All"])
        self.filter_user.set("All")
        self.filter_user.pack(side=tk.LEFT, padx=5)

        ttk.Label(filter_frame, text="Status:").pack(side=tk.LEFT, padx=(10, 0))
        self.filter_status = ttk.Combobox(filter_frame, width=15,
            values=["All", "COMPLETE", "PARTIAL_SESSION", "INCOMPLETE_CONTEXT", "CANCELLED"])
        self.filter_status.set("All")
        self.filter_status.pack(side=tk.LEFT, padx=5)

        ttk.Label(filter_frame, text="Microscope:").pack(side=tk.LEFT, padx=(10, 0))
        self.filter_microscope = ttk.Combobox(filter_frame, width=12, values=["All", "VEGA3", "MIRA3_FEG"])
        self.filter_microscope.set("All")
        self.filter_microscope.pack(side=tk.LEFT, padx=5)

        ttk.Button(filter_frame, text="Filter", command=self.refresh).pack(side=tk.LEFT, padx=10)
        ttk.Button(filter_frame, text="Export CSV", command=self._on_export_csv).pack(side=tk.RIGHT, padx=5)

        # Treeview
        tree_frame = ttk.Frame(self, padding=5)
        tree_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)

        columns = ("id", "user", "start", "end", "duration", "tier", "rate",
                   "discount", "cost", "status", "type")
        self.tree = ttk.Treeview(tree_frame, columns=columns, show="headings")

        headers = [
            ("id", "ID", 40), ("user", "User", 100), ("start", "Start", 140),
            ("end", "End", 140), ("duration", "Duration (min)", 90),
            ("tier", "Tier", 80), ("rate", "Rate PLN/h", 80),
            ("discount", "Discount %", 70), ("cost", "Cost (PLN)", 90),
            ("status", "Status", 110), ("type", "Type", 80),
        ]
        for col, text, width in headers:
            self.tree.heading(col, text=text)
            self.tree.column(col, width=width, minwidth=40)

        scrollbar_y = ttk.Scrollbar(tree_frame, orient=tk.VERTICAL, command=self.tree.yview)
        scrollbar_x = ttk.Scrollbar(tree_frame, orient=tk.HORIZONTAL, command=self.tree.xview)
        self.tree.configure(yscrollcommand=scrollbar_y.set, xscrollcommand=scrollbar_x.set)

        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar_y.pack(side=tk.RIGHT, fill=tk.Y)

        # Right-click menu
        self.context_menu = tk.Menu(self, tearoff=0)
        self.context_menu.add_command(label="Set Discount %", command=self._ppm_discount)
        self.context_menu.add_command(label="Set Fixed Cost (PLN)", command=self._ppm_cost_override)
        self.context_menu.add_command(label="Set Manual Time (min)", command=self._ppm_time_override)
        self.context_menu.add_separator()
        self.context_menu.add_command(label="Change Tier: PROJECT", command=lambda: self._ppm_tier("PROJECT"))
        self.context_menu.add_command(label="Change Tier: UJ_UNIT", command=lambda: self._ppm_tier("UJ_UNIT"))
        self.context_menu.add_command(label="Change Tier: EXTERNAL", command=lambda: self._ppm_tier("EXTERNAL"))
        self.context_menu.add_separator()
        self.context_menu.add_command(label="Change Rate (PLN/h)", command=self._ppm_rate_override)
        self.context_menu.add_command(label="Exclude from Invoice", command=self._ppm_exclude_invoice)
        self.context_menu.add_command(label="Cancel Session", command=self._ppm_cancel)

        self.tree.bind("<Button-3>", self._show_context_menu)

        # Summary bar
        summary_frame = ttk.Frame(self, padding=5)
        summary_frame.pack(fill=tk.X, padx=10, pady=(0, 10))
        self.summary_var = tk.StringVar(value="")
        ttk.Label(summary_frame, textvariable=self.summary_var, font=("Segoe UI", 9, "bold")).pack(side=tk.LEFT)

    def refresh(self):
        """Reload sessions from database with current filters."""
        for item in self.tree.get_children():
            self.tree.delete(item)

        if not self.db:
            return

        query = "SELECT * FROM sessions WHERE 1=1"
        params = []

        user_filter = self.filter_user.get()
        if user_filter and user_filter != "All":
            query += " AND username = ?"
            params.append(user_filter)

        status_filter = self.filter_status.get()
        if status_filter and status_filter != "All":
            query += " AND status = ?"
            params.append(status_filter)

        micro_filter = self.filter_microscope.get()
        if micro_filter and micro_filter != "All":
            query += " AND microscope_type = ?"
            params.append(micro_filter)

        query += " ORDER BY start_time DESC LIMIT 500"

        try:
            rows = self.db.conn.execute(query, params).fetchall()
            total_cost = 0.0
            total_hours = 0.0

            for row in rows:
                start = row["start_time"][:16] if row["start_time"] else ""
                end = row["end_time"][:16] if row["end_time"] else ""
                duration = f"{(row['duration_seconds'] or 0) / 60:.1f}"
                cost = row["calculated_cost"] or 0
                total_cost += cost
                total_hours += (row["duration_seconds"] or 0) / 3600.0

                self.tree.insert("", tk.END, iid=str(row["id"]), values=(
                    row["id"], row["username"], start, end, duration,
                    row["billing_tier"] or "PROJECT",
                    row["rate_override"] or row["hourly_rate"] or 150,
                    row["discount_percent"] or 0,
                    f"{cost:.2f}", row["status"], row["microscope_type"]
                ))

            self.summary_var.set(
                f"Showing {len(rows)} sessions | "
                f"Total: {total_hours:.1f}h | Cost: {total_cost:.2f} PLN"
            )

            # Update user filter options
            users = self.db.conn.execute(
                "SELECT DISTINCT username FROM sessions ORDER BY username"
            ).fetchall()
            user_list = ["All"] + [r["username"] for r in users]
            self.filter_user["values"] = user_list

        except Exception as e:
            logger.error("Error loading sessions: %s", e)

    def _get_selected_session_id(self):
        """Get currently selected session ID."""
        selection = self.tree.selection()
        if not selection:
            messagebox.showinfo("Info", "Select a session first")
            return None
        return int(selection[0])

    def _show_context_menu(self, event):
        """Show right-click context menu."""
        item = self.tree.identify_row(event.y)
        if item:
            self.tree.selection_set(item)
            self.context_menu.post(event.x_root, event.y_root)

    def _ppm_discount(self):
        """PPM: Set discount percent."""
        sid = self._get_selected_session_id()
        if not sid:
            return
        value = simpledialog.askfloat("Discount", "Enter discount % (reduces time, not rate):",
                                      minvalue=0, maxvalue=100)
        if value is not None:
            from repositories.repositories import AuditRepository, SessionRepository
            audit = AuditRepository(self.db)
            repo = SessionRepository(self.db, audit)
            repo.update_discount(sid, value, self.current_user_var.get() or "admin")
            self.refresh()

    def _ppm_cost_override(self):
        """PPM: Set fixed cost."""
        sid = self._get_selected_session_id()
        if not sid:
            return
        value = simpledialog.askfloat("Fixed Cost", "Enter cost in PLN:", minvalue=0)
        if value is not None:
            from repositories.repositories import AuditRepository, SessionRepository
            audit = AuditRepository(self.db)
            repo = SessionRepository(self.db, audit)
            repo.update_cost_override(sid, value, self.current_user_var.get() or "admin")
            self.refresh()

    def _ppm_time_override(self):
        """PPM: Set manual time."""
        sid = self._get_selected_session_id()
        if not sid:
            return
        value = simpledialog.askfloat("Manual Time", "Enter time in minutes:", minvalue=0)
        if value is not None:
            from repositories.repositories import AuditRepository, SessionRepository
            audit = AuditRepository(self.db)
            repo = SessionRepository(self.db, audit)
            repo.update_time_override(sid, value, self.current_user_var.get() or "admin")
            self.refresh()

    def _ppm_tier(self, tier_name):
        """PPM: Change billing tier."""
        sid = self._get_selected_session_id()
        if not sid:
            return
        from repositories.repositories import AuditRepository, SessionRepository
        from models.enums import BillingTier
        audit = AuditRepository(self.db)
        repo = SessionRepository(self.db, audit)
        repo.update_billing_tier(sid, BillingTier(tier_name), self.current_user_var.get() or "admin")
        self.refresh()

    def _ppm_rate_override(self):
        """PPM: Change hourly rate."""
        sid = self._get_selected_session_id()
        if not sid:
            return
        value = simpledialog.askfloat("Rate Override", "Enter rate in PLN/h:", minvalue=0)
        if value is not None:
            from repositories.repositories import AuditRepository, SessionRepository
            audit = AuditRepository(self.db)
            repo = SessionRepository(self.db, audit)
            repo.update_rate_override(sid, value, self.current_user_var.get() or "admin")
            self.refresh()

    def _ppm_exclude_invoice(self):
        """PPM: Toggle exclude from invoice."""
        sid = self._get_selected_session_id()
        if not sid:
            return
        from repositories.repositories import AuditRepository, SessionRepository
        audit = AuditRepository(self.db)
        repo = SessionRepository(self.db, audit)
        repo.toggle_exclude_invoice(sid, self.current_user_var.get() or "admin")
        self.refresh()

    def _ppm_cancel(self):
        """PPM: Cancel session."""
        sid = self._get_selected_session_id()
        if not sid:
            return
        if messagebox.askyesno("Cancel Session", "Are you sure you want to cancel this session?"):
            from repositories.repositories import AuditRepository, SessionRepository
            audit = AuditRepository(self.db)
            repo = SessionRepository(self.db, audit)
            repo.cancel_session(sid, self.current_user_var.get() or "admin")
            self.refresh()

    def _on_export_csv(self):
        """Export visible sessions to CSV."""
        from tkinter import filedialog
        path = filedialog.asksaveasfilename(
            defaultextension=".csv",
            filetypes=[("CSV", "*.csv")],
            initialfile="sessions_export.csv"
        )
        if not path:
            return

        try:
            from exporters.exporters import CSVExporter
            from repositories.repositories import AuditRepository, SessionRepository
            audit = AuditRepository(self.db)
            repo = SessionRepository(self.db, audit)
            sessions = repo.get_all(limit=5000)
            CSVExporter.export_sessions(sessions, path)
            messagebox.showinfo("Export", f"Exported to {path}")
        except Exception as e:
            messagebox.showerror("Error", f"Export failed: {e}")
