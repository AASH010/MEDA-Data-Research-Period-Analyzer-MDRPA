"""User guide dialog for the MEDA Data Research & Period Analyzer."""

from __future__ import annotations

from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QTextBrowser,
    QVBoxLayout,
)

from application.version import APP_NAME


__all__ = ["HelpDialog"]


class HelpDialog(QDialog):
    """Display the application's user guide."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)

        self.setObjectName("help_dialog")
        self.setWindowTitle(f"{APP_NAME} - User Guide")
        self.setMinimumSize(640, 560)
        self.setModal(True)

        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 18, 18, 16)
        layout.setSpacing(12)

        self.help_browser = QTextBrowser(self)
        self.help_browser.setObjectName("help_browser")
        self.help_browser.setOpenExternalLinks(True)
        self.help_browser.setHtml(self._help_html())

        layout.addWidget(self.help_browser)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Close,
            parent=self,
        )
        buttons.rejected.connect(self.reject)
        buttons.accepted.connect(self.accept)

        layout.addWidget(buttons)

    @staticmethod
    def _help_html() -> str:
        return f"""
        <html>
        <body>
            <h2>{APP_NAME} - User Guide</h2>

            <p>
                This guide introduces the main areas of the application
                and the typical analysis workflow.
            </p>

            <h3>1. Overview</h3>
            <p>
                The Overview page provides a summary of available
                analysis runs and shortcuts to the main application
                sections.
            </p>

            <h3>2. Input Data</h3>
            <p>
                Use the Input Data section to select and review the
                source data required for an analysis. Check the selected
                input before starting a run.
            </p>

            <h3>3. Analysis Configuration</h3>
            <p>
                Configure the analysis period and available analysis
                settings before execution. Review the configuration
                carefully before submitting the run.
            </p>

            <h3>4. Analysis Execution</h3>
            <p>
                Start the analysis from the Analysis section. The
                application processes the selected data and stores
                outputs under the corresponding run.
            </p>

            <h3>5. Dashboard</h3>
            <p>
                Use the Dashboard to inspect the analysis results and
                available summaries for a selected run.
            </p>

            <h3>6. Reports &amp; Export</h3>
            <p>
                The Reports section lists available report artifacts
                for the selected run. Available files can be previewed
                and exported to a destination of your choice.
            </p>

            <h3>7. Run History</h3>
            <p>
                Each analysis run is stored separately. Select a run
                to inspect its status, metadata, and available outputs.
            </p>

            <h3>8. Understanding Scientific Results</h3>
            <p>
                Results should be interpreted in the context of the
                source data, data coverage, quality limitations,
                synchronization constraints, and the documented
                analysis methodology.
            </p>

            <p>
                The application supports research and analysis. Its
                outputs should not be treated as a replacement for
                reviewing the original MEDA data and scientific
                documentation.
            </p>

            <h3>Useful Resources</h3>
            <ul>
                <li>
                    <a href="https://pds.nasa.gov/">
                        NASA Planetary Data System
                    </a>
                </li>
                <li>
                    <a href="https://mars.nasa.gov/mars2020/spacecraft/instruments/meda/">
                        NASA MEDA Instrument Information
                    </a>
                </li>
            </ul>
        </body>
        </html>
        """