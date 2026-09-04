import sys

from PySide6.QtWidgets import QApplication

from logic import SchedulerLogic
from ui_main import MainApp

if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setApplicationName("课程排程")
    window = MainApp(SchedulerLogic())
    window.show()
    raise SystemExit(app.exec())
