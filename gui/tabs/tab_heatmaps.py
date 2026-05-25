"""Usage Heatmaps tab - matplotlib heatmaps with custom color scales."""

import tkinter as tk
from tkinter import ttk, colorchooser, filedialog, messagebox, simpledialog
import logging
import json
from datetime import datetime, timedelta
from collections import defaultdict

import numpy as np

logger = logging.getLogger(__name__)

DEFAULT_COLORS = [
    {"value": 0, "color": "#ffffff"},
    {"value": 0.01, "color": "#00ff00"},
    {"value": 100, "color": "#ff0000"},
]


class HeatmapsTab:
    """Usage heatmaps with configurable types, granularity, date range, custom colors."""

    def __init__(self, parent, app):
        self.app = app
        self.frame = ttk.Frame(parent, padding=10)
        self.fig = None
        self.canvas = None
        self.color_points = list(DEFAULT_COLORS)
        self._build_ui()

    def _build_ui(self):
        """Build heatmap controls and canvas."""
        # Controls frame
        ctrl = ttk.LabelFrame(self.frame, text="Heatmap Settings", padding=5)
        ctrl.pack(fill=tk.X, pady=(0, 5))

        row1 = ttk.Frame(ctrl)
        row1.pack(fill=tk.X, pady=2)

        ttk.Label(row1, text="Type:").pack(side=tk.LEFT, padx=(0, 5))
        self.type_var = tk.StringVar(value="usage_time")
        type_combo = ttk.Combobox(
            row1, textvariable=self.type_var, state="readonly", width=15,
            values=["usage_time", "pumping_time", "penalties", "idle_time", "gvl_open_time"],
        )
        type_combo.pack(side=tk.LEFT, padx=(0, 15))

        ttk.Label(row1, text="Granularity:").pack(side=tk.LEFT, padx=(0, 5))
        self.gran_var = tk.StringVar(value="daily")
        gran_combo = ttk.Combobox(
            row1, textvariable=self.gran_var, state="readonly", width=10,
            values=["hourly", "daily", "monthly"],
        )
        gran_combo.pack(side=tk.LEFT, padx=(0, 15))

        ttk.Label(row1, text="Range:").pack(side=tk.LEFT, padx=(0, 5))
        self.range_var = tk.StringVar(value="90d")
        range_combo = ttk.Combobox(
            row1, textvariable=self.range_var, state="readonly", width=8,
            values=["30d", "90d", "6m", "1y", "All"],
        )
        range_combo.pack(side=tk.LEFT, padx=(0, 15))

        self.annotate_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(row1, text="Show Values", variable=self.annotate_var).pack(
            side=tk.LEFT, padx=10
        )

        row2 = ttk.Frame(ctrl)
        row2.pack(fill=tk.X, pady=2)

        ttk.Button(row2, text="Generate", command=self._generate).pack(side=tk.LEFT, padx=5)
        ttk.Button(row2, text="Edit Colors...", command=self._edit_colors).pack(side=tk.LEFT, padx=5)
        ttk.Button(row2, text="Export PNG", command=self._export_png).pack(side=tk.LEFT, padx=5)
        ttk.Button(row2, text="Export SVG", command=self._export_svg).pack(side=tk.LEFT, padx=5)

        # Matplotlib canvas area
        self.canvas_frame = ttk.Frame(self.frame)
        self.canvas_frame.pack(fill=tk.BOTH, expand=True)

    def _get_date_range(self):
        """Calculate start date from range preset."""
        now = datetime.now()
        r = self.range_var.get()
        if r == "30d":
            return now - timedelta(days=30), now
        elif r == "90d":
            return now - timedelta(days=90), now
        elif r == "6m":
            return now - timedelta(days=180), now
        elif r == "1y":
            return now - timedelta(days=365), now
        else:  # All
            return None, None

    def _generate(self):
        """Generate heatmap from data."""
        try:
            import matplotlib
            matplotlib.use("TkAgg")
            import matplotlib.pyplot as plt
            from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
            from matplotlib.colors import LinearSegmentedColormap

            data = self._fetch_data()
            if not data:
                messagebox.showinfo("No Data", "No data found for selected parameters.")
                return

            # Clear previous canvas
            for widget in self.canvas_frame.winfo_children():
                widget.destroy()

            # Build color map from user points
            cmap = self._build_colormap()

            # Create figure
            self.fig, ax = plt.subplots(1, 1, figsize=(10, 6))
            matrix, xlabels, ylabels = self._build_matrix(data)

            vmax = matrix.max() if matrix.max() > 0 else 1
            im = ax.imshow(matrix, cmap=cmap, aspect="auto", vmin=0, vmax=vmax)
            ax.set_xticks(range(len(xlabels)))
            ax.set_xticklabels(xlabels, rotation=45, ha="right", fontsize=7)
            ax.set_yticks(range(len(ylabels)))
            ax.set_yticklabels(ylabels, fontsize=8)
            plt.colorbar(im, ax=ax)

            # Annotate cells
            if self.annotate_var.get() and matrix.size < 500:
                for i in range(matrix.shape[0]):
                    for j in range(matrix.shape[1]):
                        val = matrix[i, j]
                        if val > 0:
                            ax.text(j, i, f"{val:.1f}", ha="center", va="center", fontsize=6)

            htype = self.type_var.get().replace("_", " ").title()
            ax.set_title(f"{htype} Heatmap ({self.gran_var.get()})")
            plt.tight_layout()

            self.canvas = FigureCanvasTkAgg(self.fig, self.canvas_frame)
            self.canvas.draw()
            self.canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)
            self.app.set_status("Heatmap generated")
        except ImportError:
            messagebox.showerror("Error", "matplotlib is required for heatmaps")
        except Exception as e:
            logger.error("Heatmap generation failed: %s", e)
            messagebox.showerror("Error", str(e))

    def _fetch_data(self):
        """Fetch data from database based on type and range."""
        start, end = self._get_date_range()
        htype = self.type_var.get()
        query_map = {
            "usage_time": "SELECT start_time as ts, gvl_total_seconds as val FROM sessions",
            "pumping_time": "SELECT pump_start as ts, pump_duration_seconds as val FROM vacuum_cycles",
            "penalties": "SELECT timestamp as ts, amount_pln as val FROM penalties",
            "idle_time": "SELECT timestamp as ts, duration_seconds as val FROM anomalies WHERE anomaly_type='IDLE_AFTER_READY'",
            "gvl_open_time": "SELECT start_time as ts, gvl_total_seconds as val FROM sessions WHERE gvl_total_seconds > 0",
        }
        query = query_map.get(htype, query_map["usage_time"])
        params = []
        conditions = []
        if start:
            conditions.append("ts >= ?")
            params.append(start.isoformat())
        if end:
            conditions.append("ts <= ?")
            params.append(end.isoformat())
        if conditions:
            # Wrap query with WHERE
            base = query
            if "WHERE" in base:
                base += " AND " + " AND ".join(conditions)
            else:
                base += " WHERE " + " AND ".join(conditions)
            query = base

        try:
            with self.app.db.get_cursor() as cursor:
                cursor.execute(query, params)
                return [dict(row) for row in cursor.fetchall()]
        except Exception as e:
            logger.error("Heatmap data fetch failed: %s", e)
            return []

    def _build_matrix(self, data):
        """Build 2D matrix from data based on granularity."""
        gran = self.gran_var.get()
        aggregated = defaultdict(float)

        for row in data:
            ts = row.get("ts")
            val = row.get("val", 0) or 0
            if not ts:
                continue
            try:
                dt = datetime.fromisoformat(ts) if isinstance(ts, str) else ts
            except (ValueError, TypeError):
                continue

            if gran == "hourly":
                key = (dt.strftime("%Y-%m-%d"), dt.hour)
            elif gran == "daily":
                key = (dt.strftime("%Y-%W"), dt.weekday())
            else:  # monthly
                key = (str(dt.year), dt.month - 1)

            # Convert to minutes for time-based metrics
            if self.type_var.get() in ("usage_time", "pumping_time", "idle_time", "gvl_open_time"):
                aggregated[key] += val / 60.0
            else:
                aggregated[key] += val

        if not aggregated:
            return np.zeros((1, 1)), [""], [""]

        # Build sorted axis labels
        rows = sorted(set(k[0] for k in aggregated.keys()))
        if gran == "hourly":
            cols = list(range(24))
            col_labels = [f"{h:02d}:00" for h in cols]
        elif gran == "daily":
            cols = list(range(7))
            col_labels = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
        else:
            cols = list(range(12))
            col_labels = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
                          "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]

        matrix = np.zeros((len(rows), len(cols)))
        row_idx = {r: i for i, r in enumerate(rows)}
        for (r, c), v in aggregated.items():
            if r in row_idx and c < len(cols):
                matrix[row_idx[r], c] = v

        return matrix, col_labels, rows

    def _build_colormap(self):
        """Build matplotlib colormap from user-defined color points."""
        from matplotlib.colors import LinearSegmentedColormap
        points = sorted(self.color_points, key=lambda p: p["value"])
        if len(points) < 2:
            points = DEFAULT_COLORS[:]

        # Normalize positions to 0-1
        vmin = points[0]["value"]
        vmax = points[-1]["value"]
        span = vmax - vmin if vmax > vmin else 1.0

        colors_list = []
        positions = []
        for p in points:
            pos = (p["value"] - vmin) / span
            positions.append(pos)
            c = p["color"]
            # Convert hex to RGB tuple
            r = int(c[1:3], 16) / 255.0
            g = int(c[3:5], 16) / 255.0
            b = int(c[5:7], 16) / 255.0
            colors_list.append((r, g, b))

        # Build segmented colormap
        cdict = {"red": [], "green": [], "blue": []}
        for pos, (r, g, b) in zip(positions, colors_list):
            cdict["red"].append((pos, r, r))
            cdict["green"].append((pos, g, g))
            cdict["blue"].append((pos, b, b))

        return LinearSegmentedColormap("custom", cdict)

    def _edit_colors(self):
        """Open dialog to edit color scale points."""
        dialog = tk.Toplevel(self.frame)
        dialog.title("Edit Color Scale")
        dialog.geometry("400x300")
        dialog.transient(self.frame.winfo_toplevel())

        ttk.Label(dialog, text="Define color points (value + color):").pack(pady=5)

        listbox = tk.Listbox(dialog, height=8)
        listbox.pack(fill=tk.BOTH, expand=True, padx=10)

        for p in self.color_points:
            listbox.insert(tk.END, f"Value: {p['value']}  Color: {p['color']}")

        btn_frame = ttk.Frame(dialog)
        btn_frame.pack(fill=tk.X, padx=10, pady=5)

        def add_point():
            val = simpledialog.askfloat("Value", "Enter value:", parent=dialog)
            if val is None:
                return
            color = colorchooser.askcolor(title="Pick Color", parent=dialog)
            if color[1] is None:
                return
            self.color_points.append({"value": val, "color": color[1]})
            listbox.insert(tk.END, f"Value: {val}  Color: {color[1]}")

        def remove_point():
            sel = listbox.curselection()
            if not sel:
                return
            idx = sel[0]
            if len(self.color_points) <= 2:
                messagebox.showwarning("Minimum", "Need at least 2 color points.", parent=dialog)
                return
            self.color_points.pop(idx)
            listbox.delete(idx)

        def save_palette():
            palette_json = json.dumps(self.color_points)
            self.app.settings_repo.set("heatmap_palette", palette_json, self.app.get_operator())
            dialog.destroy()

        ttk.Button(btn_frame, text="Add Point", command=add_point).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="Remove", command=remove_point).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="Save", command=save_palette).pack(side=tk.RIGHT, padx=5)

    def _export_png(self):
        """Export heatmap as PNG."""
        if self.fig is None:
            messagebox.showwarning("No Chart", "Generate a heatmap first.")
            return
        path = filedialog.asksaveasfilename(
            defaultextension=".png", filetypes=[("PNG", "*.png")]
        )
        if path:
            self.fig.savefig(path, dpi=150, bbox_inches="tight")
            self.app.set_status(f"Exported: {path}")

    def _export_svg(self):
        """Export heatmap as SVG."""
        if self.fig is None:
            messagebox.showwarning("No Chart", "Generate a heatmap first.")
            return
        path = filedialog.asksaveasfilename(
            defaultextension=".svg", filetypes=[("SVG", "*.svg")]
        )
        if path:
            self.fig.savefig(path, format="svg", bbox_inches="tight")
            self.app.set_status(f"Exported: {path}")
