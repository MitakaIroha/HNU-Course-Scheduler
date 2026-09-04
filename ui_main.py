"""Qt desktop presentation layer with native, virtualized controls."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QAbstractTableModel, QModelIndex, QTimer, Qt
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QDialog,
    QFileDialog,
    QFormLayout,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QMenu,
    QPushButton,
    QPlainTextEdit,
    QScrollArea,
    QSplitter,
    QStyledItemDelegate,
    QTableView,
    QVBoxLayout,
    QWidget,
)

from logic import SchedulerLogic, WorkbookLoadError
from models import Course
from data_services import (
    DataFormatError,
    PersonalSchedule,
    course_key,
    export_schedule_workbook,
    load_personal_excel,
    load_personal_json,
    load_plan,
    personal_schedule_from_dict,
    save_plan,
)
from ui_schedule import ScheduleWidget

DAYS = ("周一", "周二", "周三", "周四", "周五", "周六", "周日")


class CourseTableModel(QAbstractTableModel):
    def __init__(self) -> None:
        super().__init__()
        self.courses: list[Course] = []
        self.columns: list[str] = []

    def set_content(self, courses: list[Course], columns: list[str]) -> None:
        self.beginResetModel()
        self.courses, self.columns = courses, columns
        self.endResetModel()

    def rowCount(self, parent=QModelIndex()) -> int:
        return 0 if parent.isValid() else len(self.courses)

    def columnCount(self, parent=QModelIndex()) -> int:
        return 0 if parent.isValid() else len(self.columns)

    def data(self, index: QModelIndex, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid() or role not in {Qt.ItemDataRole.DisplayRole, Qt.ItemDataRole.ToolTipRole}:
            return None
        return str(self.courses[index.row()].full_data.get(self.columns[index.column()], ""))

    def headerData(self, section: int, orientation: Qt.Orientation, role=Qt.ItemDataRole.DisplayRole):
        if role == Qt.ItemDataRole.DisplayRole and orientation == Qt.Orientation.Horizontal and section < len(self.columns):
            return self.columns[section]
        return super().headerData(section, orientation, role)

    def course_at(self, row: int) -> Course | None:
        return self.courses[row] if 0 <= row < len(self.courses) else None

    def flags(self, index: QModelIndex):
        flags = super().flags(index)
        return flags | Qt.ItemFlag.ItemIsEditable if index.isValid() else flags


class SelectableTextDelegate(QStyledItemDelegate):
    def createEditor(self, parent, option, index):
        editor = QPlainTextEdit(parent)
        editor.setReadOnly(True)
        editor.setLineWrapMode(QPlainTextEdit.LineWrapMode.WidgetWidth)
        editor.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        editor.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        editor.setStyleSheet(
            "QPlainTextEdit { background: #FFFFFF; color: #172033; "
            "border: 1px solid #3659D9; padding: 3px; selection-background-color: #3659D9; }"
        )
        return editor

    def setEditorData(self, editor: QPlainTextEdit, index: QModelIndex) -> None:
        editor.setPlainText(str(index.data(Qt.ItemDataRole.DisplayRole) or ""))
        editor.selectAll()

    def setModelData(self, editor, model, index) -> None:
        pass

    def updateEditorGeometry(self, editor, option, index) -> None:
        editor.setGeometry(option.rect)


class MainApp(QMainWindow):
    def __init__(self, logic: SchedulerLogic) -> None:
        super().__init__()
        self.logic, self.current_week = logic, 1
        self.selected_day: int | None = None
        self.selected_period: int | None = None
        self.visible_columns: dict[str, bool] = {}
        self.field_filters: dict[str, str] = {}
        self.quick_filters: dict[str, str] = {}
        self.quick_combos: dict[str, QComboBox] = {}
        self.personal_schedule: PersonalSchedule | None = None
        self.undo_stack: list[tuple[list[str], PersonalSchedule | None]] = []
        self.redo_stack: list[tuple[list[str], PersonalSchedule | None]] = []
        self.recovery_path = Path(__file__).with_name(".course_scheduler_recovery.json")
        self.table_model = CourseTableModel()
        self.search_timer = QTimer(self)
        self.search_timer.setSingleShot(True)
        self.search_timer.setInterval(160)
        self.search_timer.timeout.connect(self.refresh_courses)
        self.setWindowTitle("课程排程")
        self.resize(1440, 900)
        self.setMinimumSize(1120, 700)
        self._apply_style()
        self._build()
        QShortcut(QKeySequence.StandardKey.Open, self, activated=self.import_file)
        QShortcut(QKeySequence.StandardKey.Find, self, activated=self.search_entry.setFocus)
        QShortcut(QKeySequence(Qt.Key.Key_Escape), self, activated=self.clear_filters)

    def _apply_style(self) -> None:
        self.setStyleSheet("""
            QMainWindow, QWidget#root { background: #F5F7FB; color: #172033; font: 10pt "Microsoft YaHei UI"; }
            QFrame#header, QFrame#panel { background: #FFFFFF; border: 1px solid #DCE2EE; border-radius: 6px; }
            QFrame#header { border-width: 0 0 1px 0; border-radius: 0; }
            QLabel#title { font-size: 21px; font-weight: 700; }
            QLabel#section { font-size: 16px; font-weight: 700; }
            QLabel#credits { color: #3659D9; font-weight: 700; }
            QLabel#muted { color: #65708A; }
            QPushButton { min-height: 30px; padding: 0 12px; border: 0; border-radius: 4px; background: #EDF1F8; color: #172033; }
            QPushButton:hover { background: #E0E6F0; }
            QPushButton:pressed { background: #D4DCE9; }
            QPushButton#primary { min-height: 36px; background: #3659D9; color: white; font-weight: 700; }
            QPushButton#primary:hover { background: #2949BA; }
            QLineEdit { min-height: 34px; padding: 0 10px; border: 1px solid #DCE2EE; border-radius: 4px; background: #FFFFFF; selection-background-color: #3659D9; }
            QLineEdit:focus { border-color: #3659D9; }
            QTableView { background: #FFFFFF; alternate-background-color: #F8F9FC; border: 1px solid #DCE2EE; gridline-color: #E8ECF3; selection-background-color: #DDE7FF; selection-color: #172033; }
            QHeaderView::section { background: #F1F4F9; color: #4C5568; padding: 7px; border: 0; border-right: 1px solid #DCE2EE; border-bottom: 1px solid #DCE2EE; font-weight: 700; }
            QSplitter::handle { background: #DCE2EE; }
            QSplitter::handle:hover, QSplitter::handle:pressed { background: #3659D9; }
            QCheckBox { spacing: 7px; }
            QCheckBox::indicator { width: 16px; height: 16px; }
            QToolTip { background: #172033; color: white; border: 0; padding: 6px; }
        """)

    def _build(self) -> None:
        root = QWidget(objectName="root")
        layout = QVBoxLayout(root)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self._build_header())
        self.splitter = QSplitter(Qt.Orientation.Horizontal)
        self.splitter.setOpaqueResize(True)
        self.splitter.setHandleWidth(8)
        self.splitter.setChildrenCollapsible(False)
        self.splitter.addWidget(self._build_schedule_panel())
        self.splitter.addWidget(self._build_browser_panel())
        self.splitter.setStretchFactor(0, 3)
        self.splitter.setStretchFactor(1, 2)
        self.splitter.setSizes([820, 560])
        body = QWidget()
        body_layout = QVBoxLayout(body)
        body_layout.setContentsMargins(20, 18, 20, 10)
        body_layout.addWidget(self.splitter)
        layout.addWidget(body, 1)
        self.status_label = QLabel("就绪", objectName="muted")
        self.status_label.setContentsMargins(24, 0, 24, 8)
        layout.addWidget(self.status_label)
        self.setCentralWidget(root)

    def _build_header(self) -> QWidget:
        header = QFrame(objectName="header")
        header.setFixedHeight(70)
        layout = QHBoxLayout(header)
        layout.setContentsMargins(28, 0, 28, 0)
        title = QLabel("课程排程", objectName="title")
        layout.addWidget(title)
        self.subtitle = QLabel("导入课程清单后开始排课", objectName="muted")
        layout.addWidget(self.subtitle)
        layout.addStretch()
        for text, callback in (
            ("恢复", self.restore_recovery),
            ("导出课表", self.export_results),
        ):
            action = QPushButton(text)
            action.clicked.connect(callback)
            layout.addWidget(action)
        button = QPushButton("导入 Excel", objectName="primary")
        button.clicked.connect(self.import_file)
        layout.addWidget(button)
        return header

    def _build_schedule_panel(self) -> QWidget:
        panel = QFrame(objectName="panel")
        panel.setMinimumWidth(560)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(18, 16, 18, 18)
        toolbar = QHBoxLayout()
        toolbar.addWidget(QLabel("我的课表", objectName="section"))
        self.total_credits_label = QLabel("当前总学分：0", objectName="credits")
        toolbar.addWidget(self.total_credits_label)
        personal = QPushButton("导入个人课表")
        personal.clicked.connect(self.import_personal_schedule)
        toolbar.addWidget(personal)
        undo = QPushButton("撤销")
        undo.clicked.connect(self.undo)
        toolbar.addWidget(undo)
        redo = QPushButton("恢复撤销")
        redo.clicked.connect(self.redo)
        toolbar.addWidget(redo)
        toolbar.addStretch()
        self.show_all = QCheckBox("显示非本周课程")
        self.show_all.toggled.connect(self.render_schedule)
        toolbar.addWidget(self.show_all)
        previous = QPushButton("<")
        previous.setFixedWidth(34)
        previous.clicked.connect(lambda: self.change_week(-1))
        toolbar.addWidget(previous)
        self.week_label = QLabel("第 01 周")
        self.week_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.week_label.setFixedWidth(72)
        toolbar.addWidget(self.week_label)
        following = QPushButton(">")
        following.setFixedWidth(34)
        following.clicked.connect(lambda: self.change_week(1))
        toolbar.addWidget(following)
        layout.addLayout(toolbar)
        self.remark_courses_label = QLabel("", objectName="muted")
        self.remark_courses_label.setWordWrap(True)
        self.remark_courses_label.hide()
        layout.addWidget(self.remark_courses_label)
        self.schedule = ScheduleWidget()
        self.schedule.slot_selected.connect(self.select_slot)
        self.schedule.slot_remove_requested.connect(self.remove_from_slot)
        layout.addWidget(self.schedule, 1)
        return panel

    def _build_browser_panel(self) -> QWidget:
        panel = QFrame(objectName="panel")
        panel.setMinimumWidth(360)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(18, 16, 18, 18)
        top = QHBoxLayout()
        top.addWidget(QLabel("课程目录", objectName="section"))
        top.addStretch()
        self.result_label = QLabel("0 门课程", objectName="muted")
        top.addWidget(self.result_label)
        layout.addLayout(top)
        self.search_entry = QLineEdit()
        self.search_entry.setPlaceholderText("搜索课程、教师或地点")
        self.search_entry.textChanged.connect(lambda: self.search_timer.start())
        layout.addWidget(self.search_entry)
        quick = QGridLayout()
        quick.setHorizontalSpacing(8)
        for column, (field, label) in enumerate((("考核方式", "考核"), ("课程分类", "分类"), ("开课院系", "学院"))):
            quick.addWidget(QLabel(label, objectName="muted"), 0, column * 2)
            combo = QComboBox()
            combo.setMinimumWidth(90)
            combo.addItem("全部")
            combo.currentTextChanged.connect(lambda value, key=field: self._set_quick_filter(key, value))
            self.quick_combos[field] = combo
            quick.addWidget(combo, 0, column * 2 + 1)
        self.only_available = QCheckBox("仅显示与目前课表无冲突")
        self.only_available.toggled.connect(self.refresh_courses)
        quick.addWidget(self.only_available, 1, 0, 1, 6)
        layout.addLayout(quick)
        actions = QHBoxLayout()
        clear = QPushButton("清除筛选")
        clear.clicked.connect(self.clear_filters)
        actions.addWidget(clear)
        actions.addStretch()
        field_filter = QPushButton("字段筛选")
        field_filter.clicked.connect(self.open_field_filters)
        actions.addWidget(field_filter)
        columns = QPushButton("显示字段")
        columns.clicked.connect(self.open_column_dialog)
        actions.addWidget(columns)
        layout.addLayout(actions)
        self.table = QTableView()
        self.table.setModel(self.table_model)
        self.table.setItemDelegate(SelectableTextDelegate(self.table))
        self.table.setAlternatingRowColors(True)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSortingEnabled(False)
        self.table.setWordWrap(True)
        self.table.setTextElideMode(Qt.TextElideMode.ElideNone)
        self.table.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(64)
        self.table.horizontalHeader().setMinimumSectionSize(42)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.clicked.connect(self.open_course_text_editor)
        self.table.selectionModel().selectionChanged.connect(lambda _selected, _deselected: self.render_schedule(self.selected_course()))
        layout.addWidget(self.table, 1)
        add = QPushButton("加入我的课表", objectName="primary")
        add.clicked.connect(self.add_selected_course)
        layout.addWidget(add)
        return panel

    def import_file(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "选择课程清单", "", "Excel 工作簿 (*.xlsx *.xls);;所有文件 (*)")
        if not path:
            return
        try:
            count = self.logic.load_excel(path)
        except WorkbookLoadError as exc:
            QMessageBox.critical(self, "导入失败", str(exc))
            self.set_status("导入失败")
            return
        defaults = {"课程名称", "授课教师", "开课时间地点", "学分"}
        self.visible_columns = {name: name in defaults for name in self.logic.column_names}
        self.field_filters = {name: "" for name in self.logic.column_names}
        self.quick_filters = {name: "" for name in self.quick_combos}
        self._populate_quick_filters()
        self.undo_stack.clear()
        self.redo_stack.clear()
        if not any(self.visible_columns.values()) and self.visible_columns:
            self.visible_columns[next(iter(self.visible_columns))] = True
        self.clear_filters()
        self.subtitle.setText(f"已导入 {self.logic.source_path.name} · 共 {count} 门课程")
        self.set_status(f"已导入 {count} 门课程")

    def _populate_quick_filters(self) -> None:
        for field, combo in self.quick_combos.items():
            combo.blockSignals(True)
            combo.clear()
            combo.addItem("全部")
            values = sorted({str(course.full_data.get(field, "")).strip() for course in self.logic.all_courses if str(course.full_data.get(field, "")).strip()})
            combo.addItems(values)
            combo.setCurrentIndex(0)
            combo.blockSignals(False)

    def _set_quick_filter(self, field: str, value: str) -> None:
        self.quick_filters[field] = "" if value == "全部" else value
        self.refresh_courses()

    def import_personal_schedule(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "导入个人课表",
            "",
            "课表文件 (*.xlsx *.xls *.json);;Excel 工作簿 (*.xlsx *.xls);;JSON 文件 (*.json);;所有文件 (*)",
        )
        if not path:
            return
        try:
            self.personal_schedule = load_personal_json(path) if path.lower().endswith(".json") else load_personal_excel(path)
        except DataFormatError as exc:
            QMessageBox.critical(self, "导入失败", str(exc))
            return
        self.only_available.setChecked(True)
        self.refresh_courses()
        diagnostics = self.personal_schedule.diagnostics
        self.set_status(f"个人课表已导入：{len(self.personal_schedule.slots)} 个时间段，当前显示无冲突课程")
        QMessageBox.information(
            self,
            "个人课表已导入",
            f"学期：{self.personal_schedule.term or '未识别'}\n"
            f"占用单元：{diagnostics.get('occupied_cells', '-')}\n"
            f"解析时间段：{diagnostics.get('parsed_slots', len(self.personal_schedule.slots))}\n"
            f"备注课程：{diagnostics.get('remark_courses', 0)}",
        )
        self._save_recovery()

    def export_results(self) -> None:
        if not self.logic.my_courses and not (self.personal_schedule and self.personal_schedule.courses):
            QMessageBox.warning(self, "没有课程", "当前课表中没有可导出的课程。")
            return
        path, _ = QFileDialog.getSaveFileName(self, "导出个人课表", "我的课表.xlsx", "Excel 工作簿 (*.xlsx)")
        if not path:
            return
        if not path.lower().endswith(".xlsx"):
            path += ".xlsx"
        try:
            count = export_schedule_workbook(path, self.logic.my_courses, self.personal_schedule)
        except DataFormatError as exc:
            QMessageBox.critical(self, "导出失败", str(exc))
            return
        self.set_status(f"已导出 {count} 门课程到 {Path(path).name}")
        QMessageBox.information(self, "导出完成", f"已按个人课表格式导出 {count} 门课程。")

    def _selection_snapshot(self) -> list[str]:
        return [course_key(course) for course in self.logic.my_courses]

    def _history_snapshot(self) -> tuple[list[str], PersonalSchedule | None]:
        return self._selection_snapshot(), self.personal_schedule

    def _push_history(self) -> None:
        snapshot = self._history_snapshot()
        if not self.undo_stack or self.undo_stack[-1] != snapshot:
            self.undo_stack.append(snapshot)
            self.undo_stack = self.undo_stack[-100:]
        self.redo_stack.clear()

    def _apply_selection(self, keys: list[str]) -> None:
        wanted = set(keys)
        self.logic.my_courses = [course for course in self.logic.all_courses if course_key(course) in wanted]
        self.refresh_courses()
        self._save_recovery()

    def _apply_history(self, snapshot: tuple[list[str], PersonalSchedule | None]) -> None:
        keys, self.personal_schedule = snapshot
        self._apply_selection(keys)

    def undo(self) -> None:
        if not self.undo_stack:
            self.set_status("没有可撤销的操作")
            return
        self.redo_stack.append(self._history_snapshot())
        self._apply_history(self.undo_stack.pop())
        self.set_status("已撤销上一步操作")

    def redo(self) -> None:
        if not self.redo_stack:
            self.set_status("没有可重做的操作")
            return
        self.undo_stack.append(self._history_snapshot())
        self._apply_history(self.redo_stack.pop())
        self.set_status("已恢复上一步撤销")

    def _write_plan(self, path: Path) -> None:
        save_plan(path, catalog=str(self.logic.source_path or ""), selected=self.logic.my_courses, personal=self.personal_schedule,
            week=self.current_week, visible_columns=self.visible_columns, field_filters=self.field_filters,
            quick_filters=self.quick_filters, splitter_sizes=self.splitter.sizes())

    def _load_plan(self, path: Path) -> None:
        try:
            payload = load_plan(path)
            catalog = Path(payload.get("catalog", ""))
            if not catalog.exists():
                raise DataFormatError(f"方案引用的课程清单不存在：{catalog}")
            self.logic.load_excel(catalog)
            self.visible_columns = {name: bool(payload.get("visible_columns", {}).get(name, name in {"课程名称", "授课教师", "开课时间地点", "学分"})) for name in self.logic.column_names}
            self.field_filters = {name: str(payload.get("field_filters", {}).get(name, "")) for name in self.logic.column_names}
            self.quick_filters = {name: str(payload.get("quick_filters", {}).get(name, "")) for name in self.quick_combos}
            personal = payload.get("personal_schedule")
            self.personal_schedule = personal_schedule_from_dict(personal, "选课方案") if personal else None
            self.current_week = max(1, min(18, int(payload.get("week", 1))))
            self.week_label.setText(f"第 {self.current_week:02d} 周")
            self._populate_quick_filters()
            for name, value in self.quick_filters.items():
                combo = self.quick_combos[name]
                index = combo.findText(value or "全部")
                combo.setCurrentIndex(max(0, index))
            self._apply_selection(list(payload["selected_course_keys"]))
            sizes = payload.get("splitter_sizes")
            if isinstance(sizes, list) and len(sizes) == 2:
                self.splitter.setSizes([int(value) for value in sizes])
            self.only_available.setChecked(bool(self.personal_schedule))
            self.refresh_courses()
            self.subtitle.setText(f"已加载方案 · {self.logic.source_path.name}")
            self.set_status(f"已加载 {len(self.logic.my_courses)} 门已选课程")
        except (DataFormatError, WorkbookLoadError, OSError, ValueError) as exc:
            QMessageBox.critical(self, "加载失败", str(exc))

    def _save_recovery(self) -> None:
        if not self.logic.source_path:
            return
        try:
            self._write_plan(self.recovery_path)
        except OSError:
            pass

    def restore_recovery(self) -> None:
        if not self.recovery_path.exists():
            self.set_status("没有可恢复的自动保存方案")
            return
        self._load_plan(self.recovery_path)

    def _center_dialog(self, dialog: QDialog, width: int) -> None:
        dialog.adjustSize()
        dialog.resize(width, dialog.sizeHint().height())
        dialog.move(self.frameGeometry().center() - dialog.rect().center())

    def open_column_dialog(self) -> None:
        if not self.visible_columns:
            self.set_status("请先导入课程清单")
            return
        dialog = QDialog(self)
        dialog.setWindowTitle("显示字段")
        root = QVBoxLayout(dialog)
        title = QLabel("选择课程目录中显示的字段", objectName="section")
        root.addWidget(title)
        root.addWidget(QLabel("至少保留一个字段，设置会立即应用。", objectName="muted"))
        grid = QGridLayout()
        for index, name in enumerate(self.visible_columns):
            checkbox = QCheckBox(name)
            checkbox.setChecked(self.visible_columns[name])
            checkbox.toggled.connect(lambda checked, key=name: self._set_column_visible(key, checked))
            grid.addWidget(checkbox, index // 3, index % 3)
        root.addLayout(grid)
        footer = QHBoxLayout()
        select_all = QPushButton("全选")
        select_all.clicked.connect(lambda: self._select_all_columns(dialog))
        footer.addWidget(select_all)
        footer.addStretch()
        close = QPushButton("关闭", objectName="primary")
        close.clicked.connect(dialog.accept)
        footer.addWidget(close)
        root.addLayout(footer)
        self._center_dialog(dialog, 620)
        dialog.exec()

    def _set_column_visible(self, name: str, visible: bool) -> None:
        self.visible_columns[name] = visible
        if not any(self.visible_columns.values()):
            self.visible_columns[name] = True
        self.refresh_courses()

    def _select_all_columns(self, dialog: QDialog) -> None:
        self.visible_columns = {name: True for name in self.visible_columns}
        self.refresh_courses()
        dialog.accept()

    def open_field_filters(self) -> None:
        columns = [name for name, shown in self.visible_columns.items() if shown]
        if not columns:
            self.set_status("请先选择要显示的字段")
            return
        dialog = QDialog(self)
        dialog.setWindowTitle("字段筛选")
        root = QVBoxLayout(dialog)
        root.addWidget(QLabel("字段筛选", objectName="section"))
        root.addWidget(QLabel("每个字段可单独搜索，多个条件同时生效。", objectName="muted"))
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        content = QWidget()
        grid = QGridLayout(content)
        for index, name in enumerate(columns):
            field = QWidget()
            form = QFormLayout(field)
            entry = QLineEdit(self.field_filters.get(name, ""))
            entry.setPlaceholderText(f"筛选{name}")
            entry.textChanged.connect(lambda text, key=name: self._set_field_filter(key, text))
            form.addRow(name, entry)
            grid.addWidget(field, index // 2, index % 2)
        scroll.setWidget(content)
        root.addWidget(scroll)
        footer = QHBoxLayout()
        clear = QPushButton("清空条件")
        clear.clicked.connect(lambda: self._clear_dialog_filters(dialog))
        footer.addWidget(clear)
        footer.addStretch()
        done = QPushButton("完成", objectName="primary")
        done.clicked.connect(dialog.accept)
        footer.addWidget(done)
        root.addLayout(footer)
        dialog.resize(680, min(680, 180 + ((len(columns) + 1) // 2) * 64))
        dialog.move(self.frameGeometry().center() - dialog.rect().center())
        dialog.exec()

    def _set_field_filter(self, name: str, value: str) -> None:
        self.field_filters[name] = value
        self.search_timer.start()

    def _clear_dialog_filters(self, dialog: QDialog) -> None:
        self.field_filters = {name: "" for name in self.field_filters}
        self.refresh_courses()
        dialog.accept()

    def refresh_courses(self) -> None:
        self.update_total_credits()
        self.update_remark_courses()
        columns = [name for name, shown in self.visible_columns.items() if shown]
        matches = self.logic.filter_courses(self.search_entry.text(), self.selected_day, self.selected_period)
        for column, value in self.field_filters.items():
            needle = value.casefold().strip()
            if needle:
                matches = [course for course in matches if needle in str(course.full_data.get(column, "")).casefold()]
        for field, value in self.quick_filters.items():
            if value:
                matches = [course for course in matches if str(course.full_data.get(field, "")).strip() == value]
        if self.only_available.isChecked():
            matches = [
                course for course in matches
                if not self.logic.conflicts_with_current_schedule(course)
                and not (self.personal_schedule and self.personal_schedule.conflicts(course))
            ]
        self.table_model.set_content(matches, columns)
        self.result_label.setText(f"{len(matches)} / {len(self.logic.all_courses)} 门")
        header = self.table.horizontalHeader()
        if len(columns) <= 5:
            self.table.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
            header.setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
            self.table.verticalHeader().setDefaultSectionSize(max(62, 50 + len(columns) * 8))
        else:
            self.table.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
            header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
            self.table.resizeColumnsToContents()
            for column in range(self.table_model.columnCount()):
                self.table.setColumnWidth(column, min(260, max(110, self.table.columnWidth(column))))
            self.table.verticalHeader().setDefaultSectionSize(72)
        # Keep the timetable and catalogue as two projections of the same state.
        self.render_schedule()

    def update_total_credits(self) -> None:
        personal_courses = (
            ((course.name, course.teacher) for course in self.personal_schedule.courses)
            if self.personal_schedule
            else ()
        )
        total = self.logic.calculate_total_credits(personal_courses)
        text = format(total, "f").rstrip("0").rstrip(".") if "." in format(total, "f") else format(total, "f")
        self.total_credits_label.setText(f"当前总学分：{text or '0'}")

    def update_remark_courses(self) -> None:
        courses = [] if not self.personal_schedule else [course for course in self.personal_schedule.courses if not course.slots]
        names = list(dict.fromkeys(course.name for course in courses))
        self.remark_courses_label.setText(f"备注课程（不排入课表）：{'、'.join(names)}")
        self.remark_courses_label.setVisible(bool(names))

    def selected_course(self) -> Course | None:
        index = self.table.currentIndex()
        return self.table_model.course_at(index.row()) if index.isValid() else None

    def open_course_text_editor(self, index: QModelIndex) -> None:
        self.table.edit(index)

    def add_selected_course(self) -> None:
        course = self.selected_course()
        if not course:
            self.set_status("请先从课程目录选择一门课程")
            return
        if self.personal_schedule and self.personal_schedule.conflicts(course):
            QMessageBox.warning(self, "与目前课表冲突", "该课程与目前课表中的预选课程在同周、同星期和同节次发生冲突。")
            return
        previous = self._history_snapshot()
        success, message = self.logic.try_add(course)
        self.set_status(message)
        if success:
            self.undo_stack.append(previous)
            self.undo_stack = self.undo_stack[-100:]
            self.redo_stack.clear()
            self.refresh_courses()
            self._save_recovery()
        else:
            QMessageBox.warning(self, "无法加入课程", message)

    def remove_from_slot(self, day: int, period: int, global_position) -> None:
        courses = [course for course in self.logic.my_courses if course.has_slot(day, period, self.current_week)]
        if not courses and self.show_all.isChecked():
            courses = [course for course in self.logic.my_courses if course.has_slot(day, period)]
        personal_courses = []
        if self.personal_schedule:
            personal_courses = [
                course for course in self.personal_schedule.courses
                if any(
                    slot.weekday == day
                    and period in slot.periods
                    and (self.current_week in slot.weeks or self.show_all.isChecked())
                    for slot in course.slots
                )
            ]
        if not courses and not personal_courses:
            return

        menu = QMenu(self)
        actions: dict[object, tuple[str, object]] = {}
        for course in courses:
            action = menu.addAction(f"移除已选课程：{course.name}")
            actions[action] = ("selected", course)
        personal_names = list(dict.fromkeys(course.name for course in personal_courses))
        for name in personal_names:
            action = menu.addAction(f"退掉预选课程：{name}")
            actions[action] = ("personal", name)
        chosen = menu.exec(global_position)
        if chosen is None:
            return
        kind, value = actions[chosen]
        if kind == "selected":
            course = value
            self._push_history()
            self.logic.remove_course(course)
            self.refresh_courses()
            self._save_recovery()
            self.set_status(f"已移除“{course.name}”")
            return

        name = str(value)
        previous = self._history_snapshot()
        self.personal_schedule = self.personal_schedule.without_course(name)
        self.undo_stack.append(previous)
        self.undo_stack = self.undo_stack[-100:]
        self.redo_stack.clear()
        self.refresh_courses()
        self._save_recovery()
        self.set_status(f"已退掉预选课程“{name}”，现在可以选择其他教师或时间")

    def change_week(self, delta: int) -> None:
        self.current_week = (self.current_week - 1 + delta) % 18 + 1
        self.week_label.setText(f"第 {self.current_week:02d} 周")
        self.render_schedule()

    def select_slot(self, day: int, period: int) -> None:
        if (self.selected_day, self.selected_period) == (day, period):
            self.clear_slot_selection()
            return
        self.selected_day, self.selected_period = day, period
        self.refresh_courses()
        self.set_status(f"正在筛选 {DAYS[day - 1]}第 {period} 节的可选课程")

    def clear_slot_selection(self) -> None:
        self.selected_day = self.selected_period = None
        self.refresh_courses()
        self.set_status("已取消课表位置筛选")

    def clear_filters(self) -> None:
        self.selected_day = self.selected_period = None
        self.search_entry.clear()
        self.field_filters = {name: "" for name in self.field_filters}
        self.quick_filters = {name: "" for name in self.quick_filters}
        for combo in self.quick_combos.values():
            combo.setCurrentIndex(0)
        self.only_available.setChecked(False)
        self.refresh_courses()

    def render_schedule(self, highlight: Course | bool | None = None) -> None:
        selected_course = highlight if isinstance(highlight, Course) else None
        self.schedule.set_schedule(
            self.logic.my_courses,
            self.current_week,
            self.show_all.isChecked(),
            (self.selected_day, self.selected_period) if self.selected_day and self.selected_period else None,
            selected_course,
            self.personal_schedule.slots if self.personal_schedule else (),
            self.personal_schedule.courses if self.personal_schedule else (),
        )

    def set_status(self, message: str) -> None:
        self.status_label.setText(message)

    def closeEvent(self, event) -> None:
        self._save_recovery()
        super().closeEvent(event)
