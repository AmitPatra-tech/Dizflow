"""Dizflow desktop app entry point."""
import logging
import sys

from dizflow.paths import DATA_DIR, LOG_PATH, register_cuda_dlls

register_cuda_dlls()
if sys.stdout:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s",
                    handlers=[logging.FileHandler(LOG_PATH, encoding="utf-8"), logging.StreamHandler(sys.stdout)]
                    if sys.stdout else [logging.FileHandler(LOG_PATH, encoding="utf-8")])

from PySide6.QtCore import Qt
from PySide6.QtNetwork import QLocalServer, QLocalSocket
from PySide6.QtWidgets import QApplication

from dizflow.engine import Engine
from dizflow.settings import Settings
from dizflow.updater import Updater
from dizflow.ui.main_window import MainWindow, Onboarding
from dizflow.ui.theme import QSS, app_icon

SERVER_NAME = "dizflow-single-instance"


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("Dizflow")
    app.setQuitOnLastWindowClosed(False)
    app.setWindowIcon(app_icon())
    # Dizflow has its own light design; don't inherit Windows dark mode for dialogs and menus.
    app.setStyle("Fusion")
    app.styleHints().setColorScheme(Qt.ColorScheme.Light)
    app.setStyleSheet(QSS)

    # Only one Dizflow at a time: a second launch just brings the first window forward.
    sock = QLocalSocket()
    sock.connectToServer(SERVER_NAME)
    if sock.waitForConnected(300):
        sock.write(b"show")
        sock.flush()
        sock.waitForBytesWritten(300)
        return 0
    QLocalServer.removeServer(SERVER_NAME)
    server = QLocalServer()
    server.listen(SERVER_NAME)

    settings = Settings()
    # Honour the installer's "start when I sign in" checkbox once, right after installing.
    choice = DATA_DIR / "installer-autostart.txt"
    if choice.exists():
        settings.set("start_with_windows", choice.read_text().strip() == "1")
        choice.unlink()
    # Keep the "start with Windows" entry pointing at wherever Dizflow is running from right now.
    try:
        from dizflow.system import set_autostart
        set_autostart(settings["start_with_windows"])
    except OSError:
        logging.getLogger("dizflow").warning("could not update start-with-Windows entry")
    engine = Engine(settings)
    updater = Updater(settings)
    win = MainWindow(engine, settings, updater)
    server.newConnection.connect(lambda: (server.nextPendingConnection(), win.show_window()))

    if not settings["onboarded"]:
        win.show()
        Onboarding(engine, settings, win).exec()
        win.go(0)
    elif "--minimized" in sys.argv or settings["start_minimized"]:
        pass
    else:
        win.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
