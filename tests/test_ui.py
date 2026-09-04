import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QPlainTextEdit

from logic import SchedulerLogic
from models import Course, TimeSlot
from ui_main import MainApp
from ui_schedule import SelectableCourseLabel


class UiSmokeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.logic = SchedulerLogic()
        self.course = Course(
            "TEST-01",
            "测试课程",
            "测试教师",
            (TimeSlot(1, frozenset({1, 2}), frozenset({1}), ""),),
            {"课程名称": "测试课程", "授课教师": "测试教师"},
            "",
            "#CDECCF",
            classroom="测试教室",
        )
        self.logic.all_courses = [self.course]
        self.logic.column_names = ["课程名称", "授课教师"]
        self.window = MainApp(self.logic)

    def tearDown(self):
        self.window.close()

    def test_catalogue_cell_opens_as_selectable_read_only_text(self):
        self.window.visible_columns = {"课程名称": True, "授课教师": True}
        self.window.field_filters = {"课程名称": "", "授课教师": ""}
        self.window.refresh_courses()
        index = self.window.table_model.index(0, 0)
        self.window.table.setCurrentIndex(index)
        self.window.open_course_text_editor(index)
        self.app.processEvents()

        editors = self.window.table.findChildren(QPlainTextEdit)
        self.assertTrue(editors)
        self.assertTrue(editors[0].isReadOnly())
        self.assertEqual(editors[0].textCursor().selectedText(), "测试课程")

    def test_timetable_course_text_is_mouse_selectable(self):
        self.window.schedule.set_schedule([self.course], 1, False, None, None)
        labels = self.window.schedule.findChildren(SelectableCourseLabel)

        self.assertTrue(labels)
        self.assertTrue(labels[0].textInteractionFlags() & Qt.TextInteractionFlag.TextSelectableByMouse)


if __name__ == "__main__":
    unittest.main()
