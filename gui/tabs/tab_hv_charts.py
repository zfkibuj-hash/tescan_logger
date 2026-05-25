"""HV Charts tab - matplotlib multi-axis chart with zoom, pan, crosshair."""

import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import logging
from datetime import datetime

import numpy as np

logger = logging.getLogger(__name__)

# Pressure conversion factors from Pa
PRESSURE_UNITS = {"Pa": 1.0, "mbar": 0.01, "Torr": 0.00750062}

PARAMETERS = [
    ("hv_kv", "HV [kV]", "set_hv_kv"),
    ("emission", "Emission [uA]", "emission_current_ua"),
    ("filament", "Filament [A]", "emitter_current_a"),
    ("chamber_p", "Chamber Pressure", "chamber_pressure_pa"),
    ("gun_p", "Gun Pressure", "gun_pressure_pa"),
    ("gvl", "GVL State", "gun_valve_state"),
    ("heating", "Heating [%]", "heating_percent"),
]


class HVChartsTab:
    """HV data chart with multi-axis, zoom, pan, crosshair, export."""

    def __init__(self, parent, app):
        self.app = app
        self.frame = ttk.Frame(parent, padding=5)
        self.fig = None
        self.canvas = None
        self._crosshair_lines = []
        self._crosshair_texts = []
        self._build_ui()

    def _build_ui(self):
        """Build HV chart controls and canvas."""
        # Top controls
        ctrl = ttk.Frame(self.frame)
        ctrl.pack(fill=tk.X, pady=(0, 5))

        # Time range
        ttk.Label(ctrl, text="Start:").pack(side=tk.LEFT, padx=(0, 2))
        self.start_var = tk.StringVar(value="")
        ttk.Entry(ctrl, textvariable=self.start_var, width=20).pack(side=tk.LEFT, padx=(0, 10))
        ttk.Label(ctrl, text="End:").pack(side=tk.LEFT, padx=(0, 2))
        self.end_var = tk.StringVar(value="")
        ttk.Entry(ctrl, textvariable=self.end_var, width=20).pack(side=tk.LEFT, padx=(0, 10))

        # Downsample
        ttk.Label(ctrl, text="Downsample:").pack(side=tk.LEFT, padx=(0, 2))
        self.downsample_var = tk.StringVar(value="1")
        ds_combo = ttk.Combobox(
            ctrl, textvariable=self.downsample_var, width=5, state="readonly",
            values=["1", "5", "10", "30", "60"],
        )
        ds_combo.pack(side=tk.LEFT, padx=(0, 10))

        # Pressure unit
        ttk.Label(ctrl, text="P Unit:").pack(side=tk.LEFT, padx=(0, 2))
        self.p_unit_var = tk.StringVar(value="Pa")
        ttk.Combobox(
            ctrl, textvariable=self.p_unit_var, width=5, state="readonly",
            values=["Pa", "mbar", "Torr"],
        ).pack(side=tk.LEFT, padx=(0, 10))

        ttk.Button(ctrl, text="Plot", command=self._plot).pack(side=tk.LEFT, padx=5)
        ttk.Button(ctrl, text="Export PNG", command=self._export_png).pack(side=tk.LEFT, padx=2)
        ttk.Button(ctrl, text="Export SVG", command=self._export_svg).pack(side=tk.LEFT, padx=2)

        # Second row - parameters and scale options
        ctrl2 = ttk.Frame(self.frame)
        ctrl2.pack(fill=tk.X, pady=(0, 5))

        # Parameter checkboxes
        self.param_vars = {}
        for key, label, _ in PARAMETERS:
            var = tk.BooleanVar(value=(key in ("hv_kv", "emission", "chamber_p")))
            self.param_vars[key] = var
            ttk.Checkbutton(ctrl2, text=label, variable=var).pack(side=tk.LEFT, padx=3)

        # Scale controls row
        ctrl3 = ttk.Frame(self.frame)
        ctrl3.pack(fill=tk.X, pady=(0, 5))

        self.log_scale_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(ctrl3, text="Log Scale (Pressure)", variable=self.log_scale_var).pack(
            side=tk.LEFT, padx=5
        )

        self.auto_scale_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(ctrl3, text="Auto Scale Y", variable=self.auto_scale_var).pack(
            side=tk.LEFT, padx=5
        )

        ttk.Label(ctrl3, text="Y Min:").pack(side=tk.LEFT, padx=(10, 2))
        self.ymin_var = tk.StringVar(value="")
        ttk.Entry(ctrl3, textvariable=self.ymin_var, width=8).pack(side=tk.LEFT, padx=(0, 5))
        ttk.Label(ctrl3, text="Y Max:").pack(side=tk.LEFT, padx=(0, 2))
        self.ymax_var = tk.StringVar(value="")
        ttk.Entry(ctrl3, textvariable=self.ymax_var, width=8).pack(side=tk.LEFT, padx=(0, 5))

        self.crosshair_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(ctrl3, text="Crosshair", variable=self.crosshair_var).pack(
            side=tk.LEFT, padx=10
        )

        # Chart canvas area
        self.canvas_frame = ttk.Frame(self.frame)
        self.canvas_frame.pack(fill=tk.BOTH, expand=True)

    def load_session_range(self, start_time, end_time):
        """Load time range from session (called by Sessions tab PPM menu)."""
        self.start_var.set(start_time[:19] if start_time else "")
        self.end_var.set(end_time[:19] if end_time else "")
        self._plot()

    def _plot(self):
        """Generate the HV chart."""
        try:
            import matplotlib
            matplotlib.use("TkAgg")
            import matplotlib.pyplot as plt
            from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg, NavigationToolbar2Tk
            import matplotlib.dates as mdates
        except ImportError:
            messagebox.showerror("Error", "matplotlib is required for HV charts")
            return

        # Fetch data
        start = self.start_var.get().strip() or None
        end = self.end_var.get().strip() or None
        downsample = int(self.downsample_var.get())

        samples = self.app.hv_repo.get_samples(
            start_time=start, end_time=end, downsample=downsample
        )
        if not samples:
            messagebox.showinfo("No Data", "No HV samples in selected range.")
            return

        # Parse timestamps
        timestamps = []
        for s in samples:
            ts = s.get("timestamp", "")
            try:
                timestamps.append(datetime.fromisoformat(ts) if isinstance(ts, str) else ts)
            except (ValueError, TypeError):
                timestamps.append(None)

        # Clear previous
        for widget in self.canvas_frame.winfo_children():
            widget.destroy()

        # Determine which parameters to plot
        active_params = [(k, lbl, col) for k, lbl, col in PARAMETERS if self.param_vars[k].get()]
        if not active_params:
            messagebox.showwarning("No Parameters", "Select at least one parameter.")
            return

        self.fig, host_ax = plt.subplots(figsize=(12, 6))
        axes = [host_ax]
        colors = ["#1f77b4", "#ff7f0e", "#2ca02c", "#d62728", "#9467bd", "#8c564b", "#e377c2"]
        lines = []
        labels = []

        p_factor = PRESSURE_UNITS.get(self.p_unit_var.get(), 1.0)
        p_unit = self.p_unit_var.get()

        for idx, (key, label, col) in enumerate(active_params):
            # Get data array
            if col == "gun_valve_state":
                ydata = [1.0 if s.get(col) == "Open" else 0.0 for s in samples]
            elif col in ("chamber_pressure_pa", "gun_pressure_pa"):
                ydata = [(s.get(col, 0) or 0) * p_factor for s in samples]
                label = label.replace("Pressure", f"Pressure [{p_unit}]")
            else:
                ydata = [s.get(col, 0) or 0 for s in samples]

            # Choose axis
            if idx == 0:
                ax = host_ax
            elif idx == 1:
                ax = host_ax.twinx()
                axes.append(ax)
            else:
                ax = host_ax.twinx()
                ax.spines["right"].set_position(("outward", 60 * (idx - 1)))
                axes.append(ax)

            color = colors[idx % len(colors)]
            ax.set_ylabel(label, color=color)
            ax.tick_params(axis="y", labelcolor=color)

            # Plot mode
            if col == "gun_valve_state":
                line, = ax.step(timestamps, ydata, where="post", color=color, label=label, alpha=0.8)
            else:
                line, = ax.plot(timestamps, ydata, color=color, label=label, linewidth=0.8)

            # Log scale for pressure
            if col in ("chamber_pressure_pa", "gun_pressure_pa") and self.log_scale_var.get():
                ax.set_yscale("log")

            # Manual Y scale
            if not self.auto_scale_var.get() and idx == 0:
                try:
                    ymin = float(self.ymin_var.get()) if self.ymin_var.get() else None
                    ymax = float(self.ymax_var.get()) if self.ymax_var.get() else None
                    if ymin is not None and ymax is not None:
                        ax.set_ylim(ymin, ymax)
                except ValueError:
                    pass

            lines.append(line)
            labels.append(label)

        host_ax.set_xlabel("Time")
        host_ax.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M:%S"))
        self.fig.autofmt_xdate()

        # Legend
        if lines:
            host_ax.legend(lines, labels, loc="upper left", fontsize=8)

        plt.tight_layout()

        # Embed in tkinter
        self.canvas = FigureCanvasTkAgg(self.fig, self.canvas_frame)
        self.canvas.draw()

        # Toolbar for zoom/pan
        toolbar = NavigationToolbar2Tk(self.canvas, self.canvas_frame)
        toolbar.update()
        self.canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)

        # Crosshair
        if self.crosshair_var.get():
            self._setup_crosshair(host_ax)

        # Scroll zoom
        self.canvas.mpl_connect("scroll_event", self._on_scroll)
        self.app.set_status(f"Plotted {len(samples)} HV samples")

    def _setup_crosshair(self, ax):
        """Setup crosshair that follows mouse cursor."""
        vline = ax.axvline(color="gray", lw=0.5, ls="--", visible=False)
        hline = ax.axhline(color="gray", lw=0.5, ls="--", visible=False)
        text = ax.text(0, 0, "", fontsize=7, visible=False,
                       bbox=dict(boxstyle="round", fc="wheat", alpha=0.8))

        def on_move(event):
            if event.inaxes != ax:
                vline.set_visible(False)
                hline.set_visible(False)
                text.set_visible(False)
                self.canvas.draw_idle()
                return
            vline.set_xdata([event.xdata])
            hline.set_ydata([event.ydata])
            vline.set_visible(True)
            hline.set_visible(True)
            try:
                import matplotlib.dates as mdates
                time_str = mdates.num2date(event.xdata).strftime("%H:%M:%S")
                text.set_text(f"t={time_str}\ny={event.ydata:.4g}")
                text.set_position((event.xdata, event.ydata))
                text.set_visible(True)
            except Exception:
                text.set_visible(False)
            self.canvas.draw_idle()

        self.canvas.mpl_connect("motion_notify_event", on_move)

    def _on_scroll(self, event):
        """Handle scroll for zoom."""
        if event.inaxes is None:
            return
        ax = event.inaxes
        scale_factor = 0.9 if event.button == "up" else 1.1
        xlim = ax.get_xlim()
        xdata = event.xdata
        new_width = (xlim[1] - xlim[0]) * scale_factor
        ax.set_xlim(xdata - new_width / 2, xdata + new_width / 2)
        self.canvas.draw_idle()

    def _export_png(self):
        """Export chart as PNG."""
        if self.fig is None:
            messagebox.showwarning("No Chart", "Plot a chart first.")
            return
        path = filedialog.asksaveasfilename(
            defaultextension=".png", filetypes=[("PNG", "*.png")]
        )
        if path:
            self.fig.savefig(path, dpi=150, bbox_inches="tight")
            self.app.set_status(f"Exported: {path}")

    def _export_svg(self):
        """Export chart as SVG."""
        if self.fig is None:
            messagebox.showwarning("No Chart", "Plot a chart first.")
            return
        path = filedialog.asksaveasfilename(
            defaultextension=".svg", filetypes=[("SVG", "*.svg")]
        )
        if path:
            self.fig.savefig(path, format="svg", bbox_inches="tight")
            self.app.set_status(f"Exported: {path}")
