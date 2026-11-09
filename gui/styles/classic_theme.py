
"""Shared visual configuration for MDRPA dashboards and charts."""

from __future__ import annotations

import pyqtgraph as pg

from PySide6.QtGui import QFont
from PySide6.QtWidgets import QSizePolicy, QWidget

__all__ = ["apply_dashboard_theme", "configure_plot"]


def configure_plot(plot: pg.PlotWidget) -> None:
    """Apply consistent styling and sizing to a dashboard plot."""

    plot.setBackground(None)
    plot.setMinimumHeight(300)
    plot.setSizePolicy(
        QSizePolicy.Policy.Expanding,
        QSizePolicy.Policy.Expanding,
    )

    plot_item = plot.getPlotItem()
    plot_item.setContentsMargins(12, 12, 12, 12)

    axis_font = QFont("Segoe UI", 9)
    label_font = QFont("Segoe UI", 10)

    for axis_name in ("left", "bottom"):
        axis = plot_item.getAxis(axis_name)
        axis.setTickFont(axis_font)
        axis.setTextPen("#C8D5DC")
        axis.setPen("#607782")

        # Axis labels are QGraphicsTextItem objects.
        axis.label.setFont(label_font)
        axis.label.setDefaultTextColor(
            pg.mkColor("#E8EEF2")
        )

    plot_item.showGrid(x=True, y=True, alpha=0.18)


def apply_dashboard_theme(dashboard: QWidget) -> None:
    """Apply the shared theme to all PlotWidgets in a dashboard."""

    pg.setConfigOptions(antialias=True)

    for plot in dashboard.findChildren(pg.PlotWidget):
        configure_plot(plot)
