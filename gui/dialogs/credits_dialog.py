"""Credits dialog for the MEDA Data Research & Period Analyzer."""

from __future__ import annotations

from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QTextBrowser,
    QVBoxLayout,
)

from application.version import APP_NAME


__all__ = ["CreditsDialog"]


class CreditsDialog(QDialog):
    """Display project authorship, data acknowledgements, and credits."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)

        self.setObjectName("credits_dialog")
        self.setWindowTitle("Credits")
        self.setMinimumSize(540, 520)
        self.setModal(True)

        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 18, 18, 16)
        layout.setSpacing(12)

        self.credits_browser = QTextBrowser(self)
        self.credits_browser.setObjectName("credits_browser")
        self.credits_browser.setOpenExternalLinks(True)
        self.credits_browser.setHtml(self._credits_html())

        layout.addWidget(self.credits_browser)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Close,
            parent=self,
        )
        buttons.rejected.connect(self.reject)
        buttons.accepted.connect(self.accept)

        layout.addWidget(buttons)

    @staticmethod
    def _credits_html() -> str:
        """Build the credits document."""

        return f"""
        <html>
        <body>
            <h2>{APP_NAME}</h2>

            <h3>Project Developer</h3>
            <p>
                <b>Abdelrahman El-Bahnasawi</b><br>
                Project author and developer.
            </p>

            <h3>Developer &amp; Contact</h3>
            <p>
                <b>GitHub:</b>
                <a href="https://github.com/AASH010">
                    github.com/AASH010
                </a>
            </p>
            <p>
                <b>LinkedIn:</b>
                <a href="https://www.linkedin.com/in/abdelrahman-el-bahnasawi-7280653a8/">
                    Abdelrahman El-Bahnasawi
                </a>
            </p>
            <p>
                <b>Email:</b>
                <a href="mailto:abdelrahmanelbahnasawi1@gmail.com">
                    abdelrahmanelbahnasawi1@gmail.com
                </a>
            </p>

            <hr>

            <h3>Data Acknowledgement</h3>
            <p>
                This project is designed to work with data from the
                Mars Environmental Dynamics Analyzer (MEDA) instrument
                aboard NASA's Perseverance rover.
            </p>
            <p>
                Data users should consult the original data archive
                and associated instrument documentation for source
                information, calibration details, and scientific context.
            </p>
            <p>
                <a href="https://pds.nasa.gov/">
                    NASA Planetary Data System
                </a>
            </p>
            <p>
                <a href="https://mars.nasa.gov/mars2020/spacecraft/instruments/meda/">
                    NASA MEDA Instrument Information
                </a>
            </p>

            <hr>

            <h3>Third-Party Technologies</h3>
            <ul>
                <li>Python</li>
                <li>PySide6</li>
                <li>NumPy</li>
                <li>pandas</li>
                <li>pyqtgraph</li>
                <li>PyYAML</li>
                <li>python-dateutil</li>
                <li>lxml</li>
            </ul>

            <hr>

            <h3>License</h3>
            <p>
                This project is distributed under the MIT License.
                See the LICENSE file included with the project.
            </p>

            <h3>Disclaimer</h3>
            <p>
                This is an independent software project. It is not
                affiliated with, endorsed by, or an official product
                of NASA or the Jet Propulsion Laboratory.
            </p>
        </body>
        </html>
        """