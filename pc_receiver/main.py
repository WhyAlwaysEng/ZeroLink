"""ZeroCast PC Receiver Entry Point
"""

import sys
from PyQt6.QtWidgets import QApplication
from PyQt6.QtNetwork import QLocalServer, QLocalSocket
from ui.main_window import MainWindow


def main():
    app = QApplication(sys.argv)
    app.setStyle("Fusion")

    # Single-instance lock to prevent duplicate processes from colliding on ports
    instance_server = QLocalServer()
    if not instance_server.listen("ZeroLink_SingleInstance_Mutex"):
        # Check if an instance is REALLY alive
        client_sock = QLocalSocket()
        client_sock.connectToServer("ZeroLink_SingleInstance_Mutex")
        if client_sock.waitForConnected(500):
            client_sock.write(b"ACTIVATE\n")
            client_sock.flush()
            client_sock.waitForBytesWritten(500)
            sys.exit(0)
        else:
            # Stale pipe from a killed process; remove and re-listen
            QLocalServer.removeServer("ZeroLink_SingleInstance_Mutex")
            instance_server.listen("ZeroLink_SingleInstance_Mutex")

    start_minimized = "--minimized" in sys.argv or "--tray" in sys.argv

    window = MainWindow(port=8888, start_minimized=start_minimized)
    if not start_minimized:
        window.show()

    def _handle_instance_conn():
        sock = instance_server.nextPendingConnection()
        if sock:
            window.showNormal()
            window.raise_()
            window.activateWindow()

    instance_server.newConnection.connect(_handle_instance_conn)

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
