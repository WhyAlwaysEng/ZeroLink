"""ZeroCast PC Receiver Entry Point
"""

import sys
import os
import time
from PyQt6.QtWidgets import QApplication
from PyQt6.QtNetwork import QLocalServer, QLocalSocket
from ui.main_window import MainWindow


def _kill_previous_instances(force_all: bool = False):
    """Safely kills older or orphaned ZeroLink processes."""
    current_pid = os.getpid()
    current_exe = os.path.abspath(sys.argv[0]).lower()
    killed_any = False
    try:
        import psutil
        for proc in psutil.process_iter(['pid', 'name', 'exe']):
            try:
                p_name = (proc.info.get('name') or '').lower()
                p_pid = proc.info.get('pid')
                if p_pid != current_pid and ('zerolink' in p_name):
                    other_exe = os.path.abspath(proc.info.get('exe') or '').lower()
                    # Kill if forced or running from a different executable path (new version)
                    if force_all or (other_exe and other_exe != current_exe):
                        proc.kill()
                        killed_any = True
            except Exception:
                pass
    except Exception:
        pass
    return killed_any


def main():
    # If launched with --kill or --force, kill all existing instances first
    if "--kill" in sys.argv or "--force" in sys.argv:
        _kill_previous_instances(force_all=True)
        time.sleep(0.3)

    app = QApplication(sys.argv)
    app.setStyle("Fusion")

    # Single-instance lock to prevent duplicate processes from colliding on ports
    instance_server = QLocalServer()
    if not instance_server.listen("ZeroLink_SingleInstance_Mutex"):
        # Check if an instance is REALLY alive
        client_sock = QLocalSocket()
        client_sock.connectToServer("ZeroLink_SingleInstance_Mutex")
        if client_sock.waitForConnected(500):
            # Check if this is a newly extracted/updated executable replacing an older one
            if _kill_previous_instances(force_all=False):
                # Older version process was terminated, reclaim the mutex
                time.sleep(0.3)
                QLocalServer.removeServer("ZeroLink_SingleInstance_Mutex")
                instance_server.listen("ZeroLink_SingleInstance_Mutex")
            else:
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
            raw = bytes(sock.readLine()).decode("utf-8", errors="ignore").strip()
            if raw == "REPLACE":
                window.close()
                QApplication.quit()
                return
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
