"""ZeroCast PC Receiver Entry Point
"""

import sys
from PyQt6.QtWidgets import QApplication
from ui.main_window import MainWindow


def main():
    app = QApplication(sys.argv)
    app.setStyle("Fusion")

    window = MainWindow(port=8888)
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
