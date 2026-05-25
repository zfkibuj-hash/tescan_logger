"""Settings tab - rate, user management, anomaly thresholds, backup."""

import tkinter as tk
from tkinter import ttk, simpledialog, messagebox, filedialog
import logging
import os
import shutil
from datetime import datetime

logger = logging.getLogger(__name__)


class SettingsTab:
    """Settings: billing rate, users, anomaly thresholds, backup controls."""

    def __init__(self, parent, app):
        self.app = app
        self.frame = ttk.Frame(parent, padding=10)
        self._build_ui()
        self._load_settings()

    def _build_ui(self):
        """Build settings layout."""
        # Billing section
        billing_frame = ttk.LabelFrame(self.frame, text="Billing", padding=10)
        billing_frame.pack(fill=tk.X, pady=(0, 10))

        row = ttk.Frame(billing_frame)
        row.pack(fill=tk.X, pady=2)
        ttk.Label(row, text="Rate (PLN/h):").pack(side=tk.LEFT, padx=(0, 5))
        self.rate_var = tk.StringVar(value="150.0")
        ttk.Entry(row, textvariable=self.rate_var, width=10).pack(side=tk.LEFT, padx=(0, 10))
        ttk.Button(row, text="Save Rate", command=self._save_rate).pack(side=tk.LEFT, padx=5)

        # Anomaly thresholds section
        thresh_frame = ttk.LabelFrame(self.frame, text="Anomaly Thresholds", padding=10)
        thresh_frame.pack(fill=tk.X, pady=(0, 10))

        row2 = ttk.Frame(thresh_frame)
        row2.pack(fill=tk.X, pady=2)
        ttk.Label(row2, text="Long Pump Time (seconds):").pack(side=tk.LEFT, padx=(0, 5))
        self.pump_thresh_var = tk.StringVar(value="300")
        ttk.Entry(row2, textvariable=self.pump_thresh_var, width=8).pack(side=tk.LEFT, padx=(0, 20))

        ttk.Label(row2, text="Idle After Ready (seconds):").pack(side=tk.LEFT, padx=(0, 5))
        self.idle_thresh_var = tk.StringVar(value="1800")
        ttk.Entry(row2, textvariable=self.idle_thresh_var, width=8).pack(side=tk.LEFT, padx=(0, 10))

        ttk.Button(row2, text="Save Thresholds", command=self._save_thresholds).pack(
            side=tk.LEFT, padx=5
        )

        # User management section
        users_frame = ttk.LabelFrame(self.frame, text="User Management", padding=10)
        users_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 10))

        # User list
        cols = ("username", "display_name", "discount", "excluded")
        self.users_tree = ttk.Treeview(users_frame, columns=cols, show="headings", height=8)
        self.users_tree.heading("username", text="Username")
        self.users_tree.heading("display_name", text="Display Name")
        self.users_tree.heading("discount", text="Discount %")
        self.users_tree.heading("excluded", text="Excluded")
        self.users_tree.column("username", width=120)
        self.users_tree.column("display_name", width=150)
        self.users_tree.column("discount", width=80)
        self.users_tree.column("excluded", width=80)

        usb = ttk.Scrollbar(users_frame, orient=tk.VERTICAL, command=self.users_tree.yview)
        self.users_tree.configure(yscrollcommand=usb.set)
        self.users_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        usb.pack(side=tk.RIGHT, fill=tk.Y)

        # User action buttons
        user_btn_frame = ttk.Frame(users_frame)
        user_btn_frame.pack(side=tk.RIGHT, fill=tk.Y, padx=(10, 0))

        ttk.Button(user_btn_frame, text="Add User", command=self._add_user).pack(pady=2, fill=tk.X)
        ttk.Button(user_btn_frame, text="Edit Discount", command=self._edit_discount).pack(
            pady=2, fill=tk.X
        )
        ttk.Button(user_btn_frame, text="Toggle Excluded", command=self._toggle_excluded).pack(
            pady=2, fill=tk.X
        )
        ttk.Button(user_btn_frame, text="Refresh", command=self._refresh_users).pack(
            pady=2, fill=tk.X
        )

        # Backup section
        backup_frame = ttk.LabelFrame(self.frame, text="Backup", padding=10)
        backup_frame.pack(fill=tk.X)

        brow = ttk.Frame(backup_frame)
        brow.pack(fill=tk.X, pady=2)
        ttk.Button(brow, text="Create Backup Now", command=self._create_backup).pack(
            side=tk.LEFT, padx=5
        )
        ttk.Button(brow, text="Restore from File...", command=self._restore_backup).pack(
            side=tk.LEFT, padx=5
        )

        self.auto_backup_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(
            brow, text="Auto-backup on start", variable=self.auto_backup_var,
            command=self._toggle_auto_backup
        ).pack(side=tk.LEFT, padx=15)

        self.backup_status = ttk.Label(backup_frame, text="")
        self.backup_status.pack(anchor=tk.W, pady=2)

    def _load_settings(self):
        """Load current settings from database."""
        try:
            rate = self.app.settings_repo.get("rate_pln_per_hour", "150.0")
            self.rate_var.set(rate)

            pump = self.app.settings_repo.get("pump_time_warning_seconds", "300")
            self.pump_thresh_var.set(pump)

            idle = self.app.settings_repo.get("idle_after_ready_threshold_seconds", "1800")
            self.idle_thresh_var.set(idle)

            auto_bk = self.app.settings_repo.get("auto_backup_on_start", "1")
            self.auto_backup_var.set(auto_bk == "1")

            self._refresh_users()
        except Exception as e:
            logger.error("Failed to load settings: %s", e)

    def _save_rate(self):
        """Save billing rate."""
        try:
            rate = float(self.rate_var.get())
            if rate <= 0:
                raise ValueError("Rate must be positive")
            operator = self.app.get_operator()
            self.app.settings_repo.set("rate_pln_per_hour", str(rate), operator)
            self.app.billing_service.update_rate(rate)
            self.app.set_status(f"Rate updated to {rate} PLN/h")
        except ValueError as e:
            messagebox.showerror("Invalid Value", str(e))

    def _save_thresholds(self):
        """Save anomaly detection thresholds."""
        try:
            pump_val = int(self.pump_thresh_var.get())
            idle_val = int(self.idle_thresh_var.get())
            if pump_val <= 0 or idle_val <= 0:
                raise ValueError("Thresholds must be positive")
            operator = self.app.get_operator()
            self.app.settings_repo.set("pump_time_warning_seconds", str(pump_val), operator)
            self.app.settings_repo.set("idle_after_ready_threshold_seconds", str(idle_val), operator)
            self.app.set_status("Thresholds saved")
        except ValueError as e:
            messagebox.showerror("Invalid Value", str(e))

    def _refresh_users(self):
        """Refresh users treeview."""
        for item in self.users_tree.get_children():
            self.users_tree.delete(item)
        try:
            users = self.app.user_repo.get_all()
            for u in users:
                self.users_tree.insert("", tk.END, values=(
                    u["username"], u.get("display_name", ""),
                    u.get("discount_percent", 0),
                    "Yes" if u.get("excluded_from_billing") else "No",
                ))
        except Exception as e:
            logger.error("Failed to load users: %s", e)

    def _add_user(self):
        """Add a new user."""
        username = simpledialog.askstring("Add User", "Username:")
        if not username:
            return
        display = simpledialog.askstring("Add User", "Display name:", initialvalue=username)
        if display is None:
            display = username
        try:
            operator = self.app.get_operator()
            self.app.user_repo.create(username, display, operator)
            self._refresh_users()
            self.app.set_status(f"User '{username}' added")
        except Exception as e:
            messagebox.showerror("Error", str(e))

    def _edit_discount(self):
        """Edit discount for selected user."""
        selected = self.users_tree.selection()
        if not selected:
            messagebox.showwarning("No Selection", "Select a user first.")
            return
        item = self.users_tree.item(selected[0])
        username = item["values"][0]
        value = simpledialog.askfloat(
            "Edit Discount", f"Discount % for {username}:", minvalue=0, maxvalue=100
        )
        if value is None:
            return
        operator = self.app.get_operator()
        self.app.user_repo.update_discount(username, value, operator)
        self._refresh_users()
        self.app.set_status(f"Discount for {username} set to {value}%")

    def _toggle_excluded(self):
        """Toggle excluded from billing for selected user."""
        selected = self.users_tree.selection()
        if not selected:
            messagebox.showwarning("No Selection", "Select a user first.")
            return
        item = self.users_tree.item(selected[0])
        username = item["values"][0]
        current_excluded = item["values"][3] == "Yes"
        operator = self.app.get_operator()
        self.app.user_repo.set_excluded(username, not current_excluded, operator)
        self._refresh_users()
        state = "excluded" if not current_excluded else "included"
        self.app.set_status(f"User {username} {state} from billing")

    def _toggle_auto_backup(self):
        """Toggle auto-backup setting."""
        val = "1" if self.auto_backup_var.get() else "0"
        operator = self.app.get_operator()
        self.app.settings_repo.set("auto_backup_on_start", val, operator)

    def _create_backup(self):
        """Create a manual database backup."""
        try:
            base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            backup_dir = os.path.join(base_dir, "backups")
            os.makedirs(backup_dir, exist_ok=True)
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            dest = os.path.join(backup_dir, f"tescan_vega3_{timestamp}.db")
            shutil.copy2(self.app.db.db_path, dest)
            self.backup_status.config(text=f"Backup created: {os.path.basename(dest)}")
            self.app.set_status("Backup created successfully")
        except Exception as e:
            messagebox.showerror("Backup Error", str(e))

    def _restore_backup(self):
        """Restore database from a backup file."""
        path = filedialog.askopenfilename(
            title="Select Backup File",
            filetypes=[("SQLite DB", "*.db"), ("All files", "*.*")],
        )
        if not path:
            return
        confirm = messagebox.askyesno(
            "Restore Backup",
            "This will OVERWRITE the current database. Continue?",
        )
        if not confirm:
            return
        try:
            self.app.db.close()
            shutil.copy2(path, self.app.db.db_path)
            self.app.db.initialize()
            self.backup_status.config(text=f"Restored from: {os.path.basename(path)}")
            self.app.set_status("Database restored from backup")
            self._load_settings()
        except Exception as e:
            messagebox.showerror("Restore Error", str(e))
