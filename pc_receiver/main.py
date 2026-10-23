"""ZeroCast PC Receiver Entry Point
"""

import sys
from PyQt6.QtWidgets import QApplication
from ui.main_window import MainWindow


def main():
    app = QApplication(sys.argv)
    app.setStyle("Fusion")

    start_minimized = "--minimized" in sys.argv or "--tray" in sys.argv

    window = MainWindow(port=8888, start_minimized=start_minimized)
    if not start_minimized:
        window.show()

    # Handle --send command line argument from Windows Context Menu
    if "--send" in sys.argv:
        try:
            idx = sys.argv.index("--send")
            if idx + 1 < len(sys.argv):
                send_path = sys.argv[idx + 1]
                from PyQt6.QtCore import QTimer
                QTimer.singleShot(400, lambda: window.send_file_via_zerodrop(send_path))
        except Exception as e:
            print(f"Error handling --send argument: {e}")

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
