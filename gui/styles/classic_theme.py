"""Shared visual configuration for MDRPA dashboards and charts."""

from __future__ import annotations

import pyqtgraph as pg

from PySide6.QtGui import QFont
from PySide6.QtWidgets import QSizePolicy, QWidget


__all__ = ["apply_dashboard_theme", "configure_plot"]

BACKGROUND = "#17232D"
FOREGROUND = "#E8EEF2"
MUTED_TEXT = "#C8D5DC"
AXIS_COLOR = "#607782"


def configure_plot(plot: pg.PlotWidget) -> None:
    """Apply consistent dark styling and readable sizing to a plot."""

    plot.setBackground(BACKGROUND)
    plot.setMinimumHeight(360)
    plot.setSizePolicy(
        QSizePolicy.Policy.Expanding,
        QSizePolicy.Policy.Expanding,
    )

    plot_item = plot.getPlotItem()
    plot_item.setContentsMargins(16, 16, 16, 16)

    axis_font = QFont("Segoe UI", 10)
    label_font = QFont("Segoe UI", 11)

    for axis_name in ("left", "bottom"):
        axis = plot_item.getAxis(axis_name)
        axis.setTickFont(axis_font)
        axis.setTextPen(MUTED_TEXT)
        axis.setPen(AXIS_COLOR)

        axis.label.setFont(label_font)
        axis.label.setDefaultTextColor(
            pg.mkColor(FOREGROUND)
        )

    plot_item.showGrid(
        x=True,
        y=True,
        alpha=0.20,
    )


def apply_dashboard_theme(dashboard: QWidget) -> None:
    """Apply the shared theme to all PlotWidgets in a dashboard."""

    pg.setConfigOptions(
        antialias=True,
        background=BACKGROUND,
        foreground=FOREGROUND,
    )

    for plot in dashboard.findChildren(pg.PlotWidget):
        configure_plot(plot)
