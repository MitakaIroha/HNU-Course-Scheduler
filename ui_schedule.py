"""Hardware-accelerated Qt timetable widget."""

from __future__ import annotations

from collections.abc import Sequence

from PySide6.QtCore import QPoint, QRect, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QFont, QFontMetrics, QMouseEvent, QPainter, QPaintEvent, QPen
from PySide6.QtWidgets import QLabel, QToolTip, QWidget

from data_services import PersonalCourse
from models import Course, TimeSlot


class SelectableCourseLabel(QLabel):
    clicked = Signal(int, int)
    remove_requested = Signal(int, int, object)

    def __init__(self, day: int, period: int, parent: QWidget) -> None:
        super().__init__(parent)
        self.day, self.period = day, period
        self._press_position: QPoint | None = None
        self._double_click = False
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setWordWrap(True)
        self.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
            | Qt.TextInteractionFlag.TextSelectableByKeyboard
        )
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setCursor(Qt.CursorShape.IBeamCursor)

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.RightButton:
            self.remove_requested.emit(self.day, self.period, event.globalPosition().toPoint())
            event.accept()
            return
        self._press_position = event.position().toPoint()
        super().mousePressEvent(event)

    def mouseDoubleClickEvent(self, event: QMouseEvent) -> None:
        self._double_click = True
        super().mouseDoubleClickEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        super().mouseReleaseEvent(event)
        if event.button() != Qt.MouseButton.LeftButton:
            return
        if self._double_click:
            self._double_click = False
            return
        if self._press_position and (event.position().toPoint() - self._press_position).manhattanLength() <= 3:
            self.clicked.emit(self.day, self.period)


class ScheduleWidget(QWidget):
    slot_selected = Signal(int, int)
    slot_remove_requested = Signal(int, int, object)

    DISPLAY_DAYS = (
        (7, "周日"),
        (1, "周一"),
        (2, "周二"),
        (3, "周三"),
        (4, "周四"),
        (5, "周五"),
        (6, "周六"),
    )
    LEFT = 48.0
    TOP = 36.0

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.courses: Sequence[Course] = ()
        self.week = 1
        self.show_all = False
        self.selected: tuple[int, int] | None = None
        self.highlight: Course | None = None
        self.personal_slots: Sequence[TimeSlot] = ()
        self.personal_courses: Sequence[PersonalCourse] = ()
        self._text_labels: dict[tuple[int, int], SelectableCourseLabel] = {}
        self.setMouseTracking(True)
        self.setMinimumSize(520, 500)
        self.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent)

    def set_schedule(
        self,
        courses: Sequence[Course],
        week: int,
        show_all: bool,
        selected: tuple[int, int] | None,
        highlight: Course | None,
        personal_slots: Sequence[TimeSlot] = (),
        personal_courses: Sequence[PersonalCourse] = (),
    ) -> None:
        self.courses = courses
        self.week = week
        self.show_all = show_all
        self.selected = selected
        self.highlight = highlight
        self.personal_slots = personal_slots
        self.personal_courses = personal_courses
        self._update_text_labels()
        self.update()

    def _metrics(self) -> tuple[float, float]:
        return max(56.0, (self.width() - self.LEFT - 4) / 7), max(42.0, (self.height() - self.TOP - 4) / 11)

    def _courses_at(self, day: int, period: int) -> tuple[list[Course], list[Course]]:
        all_here = [course for course in self.courses if course.has_slot(day, period)]
        active = [course for course in all_here if course.has_slot(day, period, self.week)]
        return all_here, active

    def _personal_at(self, day: int, period: int) -> list[PersonalCourse]:
        return [
            course for course in self.personal_courses
            if any(
                slot.weekday == day
                and period in slot.periods
                and (self.week in slot.weeks or self.show_all)
                for slot in course.slots
            )
        ]

    def paintEvent(self, event: QPaintEvent) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        painter.fillRect(event.rect(), QColor("#F8F9FC"))
        cell_w, cell_h = self._metrics()
        header_font = QFont("Microsoft YaHei UI", 9, QFont.Weight.DemiBold)
        body_font = QFont("Microsoft YaHei UI", 8)
        painter.setFont(header_font)
        painter.setPen(QColor("#65708A"))
        for column, (_day, label) in enumerate(self.DISPLAY_DAYS):
            painter.drawText(QRectF(self.LEFT + column * cell_w, 0, cell_w, self.TOP), Qt.AlignmentFlag.AlignCenter, label)

        for period in range(1, 12):
            y = self.TOP + (period - 1) * cell_h
            painter.setFont(body_font)
            painter.setPen(QColor("#65708A"))
            painter.drawText(QRectF(0, y, self.LEFT, cell_h), Qt.AlignmentFlag.AlignCenter, f"{period:02d}")
            for column, (day, _label) in enumerate(self.DISPLAY_DAYS):
                x = self.LEFT + column * cell_w
                rect = QRectF(x + 2, y + 2, cell_w - 4, cell_h - 4)
                all_here, active = self._courses_at(day, period)
                visible = active or (all_here if self.show_all else [])
                personal_courses = self._personal_at(day, period)
                personal_active = any(
                    slot.weekday == day and period in slot.periods and self.week in slot.weeks
                    for course in personal_courses for slot in course.slots
                )
                personal_here = bool(personal_courses) or any(
                    slot.weekday == day
                    and period in slot.periods
                    and (self.week in slot.weeks or self.show_all)
                    for slot in self.personal_slots
                )
                selected = self.selected == (day, period)
                highlighted = self.highlight is not None and self.highlight.has_slot(day, period)
                show_regular = bool(visible) and (bool(active) or not personal_active)
                outline = "#3659D9" if highlighted else "#E15252" if selected else "#DCE2EE"
                painter.setPen(QPen(QColor(outline), 2 if selected or highlighted else 1))
                fill = visible[0].color if show_regular and active else "#F1F3F6" if show_regular else personal_courses[0].color if personal_active else "#F1F3F6" if personal_courses else "#E6EAF2" if personal_here else "#FFFFFF"
                painter.setBrush(QColor(fill))
                painter.drawRoundedRect(rect, 4, 4)

    def _label_for(self, day: int, period: int) -> SelectableCourseLabel:
        key = (day, period)
        if key not in self._text_labels:
            label = SelectableCourseLabel(day, period, self)
            label.clicked.connect(self.slot_selected.emit)
            label.remove_requested.connect(self.slot_remove_requested.emit)
            self._text_labels[key] = label
        return self._text_labels[key]

    @staticmethod
    def _fit_label_font(label: QLabel, text: str) -> None:
        available = QRect(0, 0, max(1, label.width() - 8), max(1, label.height() - 4))
        flags = int(Qt.AlignmentFlag.AlignCenter | Qt.TextFlag.TextWordWrap)
        for point_size in (8, 7, 6):
            font = QFont("Microsoft YaHei UI", point_size)
            label.setFont(font)
            if QFontMetrics(font).boundingRect(available, flags, text).height() <= available.height():
                break

    def _update_text_labels(self) -> None:
        used: set[tuple[int, int]] = set()
        cell_w, cell_h = self._metrics()
        for period in range(1, 12):
            for column, (day, _label) in enumerate(self.DISPLAY_DAYS):
                all_here, active = self._courses_at(day, period)
                visible = active or (all_here if self.show_all else [])
                personal_courses = self._personal_at(day, period)
                personal_active = any(
                    slot.weekday == day and period in slot.periods and self.week in slot.weeks
                    for course in personal_courses for slot in course.slots
                )
                personal_here = bool(personal_courses) or any(
                    slot.weekday == day
                    and period in slot.periods
                    and (self.week in slot.weeks or self.show_all)
                    for slot in self.personal_slots
                )
                show_regular = bool(visible) and (bool(active) or not personal_active)
                text = tooltip = ""
                color = "#65708A"
                if show_regular:
                    course = visible[0]
                    text = f"{course.name}\n{course.teacher}\n{course.classroom}"
                    tooltip = f"{course.name}\n教师：{course.teacher}\n地点：{course.classroom}\n周次：{course.week_summary}\n右键可移除"
                    color = "#172033" if course in active else "#65708A"
                elif personal_courses:
                    course = personal_courses[0]
                    text = f"{course.name}\n{course.teacher}\n{course.classroom}"
                    state = "" if personal_active else "\n本周不上课"
                    tooltip = f"{course.name}\n老师：{course.teacher}\n地点：{course.classroom}{state}\n{course.details}\n右键可移除整门预选课"
                    color = "#172033" if personal_active else "#65708A"
                elif personal_here:
                    text = tooltip = "已有课程"
                if not text:
                    continue
                label = self._label_for(day, period)
                x = self.LEFT + column * cell_w
                y = self.TOP + (period - 1) * cell_h
                label.setGeometry(int(x + 6), int(y + 4), max(1, int(cell_w - 12)), max(1, int(cell_h - 8)))
                if label.text() != text:
                    label.setText(text)
                label.setToolTip(tooltip)
                label.setStyleSheet(
                    f"QLabel {{ background: transparent; color: {color}; padding: 2px; }}"
                    "QLabel:focus { outline: none; }"
                )
                self._fit_label_font(label, text)
                label.show()
                label.raise_()
                used.add((day, period))
        for key, label in self._text_labels.items():
            if key not in used:
                label.hide()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._update_text_labels()

    def _slot_at(self, point: QPoint) -> tuple[int, int] | None:
        cell_w, cell_h = self._metrics()
        column = int((point.x() - self.LEFT) // cell_w)
        period = int((point.y() - self.TOP) // cell_h) + 1
        if not 0 <= column < len(self.DISPLAY_DAYS) or not 1 <= period <= 11:
            return None
        return self.DISPLAY_DAYS[column][0], period

    def mousePressEvent(self, event: QMouseEvent) -> None:
        slot = self._slot_at(event.position().toPoint())
        if not slot:
            return
        if event.button() == Qt.MouseButton.RightButton:
            self.slot_remove_requested.emit(*slot, event.globalPosition().toPoint())
        elif event.button() == Qt.MouseButton.LeftButton:
            self.slot_selected.emit(*slot)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        slot = self._slot_at(event.position().toPoint())
        if not slot:
            QToolTip.hideText()
            return
        all_here, active = self._courses_at(*slot)
        visible = active or (all_here if self.show_all else [])
        personal = self._personal_at(*slot)
        day, period = slot
        personal_current = [
            course for course in personal
            if any(
                course_slot.weekday == day
                and period in course_slot.periods
                and self.week in course_slot.weeks
                for course_slot in course.slots
            )
        ]
        if active or (visible and not personal_current):
            course = visible[0]
            QToolTip.showText(event.globalPosition().toPoint(), f"{course.name}\n教师：{course.teacher}\n地点：{course.classroom}\n周次：{course.week_summary}\n右键可移除", self)
            return
        if personal:
            course = (personal_current or personal)[0]
            state = "" if personal_current else "\n本周不上课"
            QToolTip.showText(event.globalPosition().toPoint(), f"{course.name}\n老师：{course.teacher}\n地点：{course.classroom}{state}\n{course.details}\n右键可移除整门预选课", self)
            return
        QToolTip.hideText()

    def leaveEvent(self, event) -> None:
        QToolTip.hideText()
        super().leaveEvent(event)
