"""Application service layer. It deliberately contains no UI code."""

from __future__ import annotations

import hashlib
import re
from collections.abc import Iterable
from decimal import Decimal, InvalidOperation
from pathlib import Path

import pandas as pd

from models import Course
from parser_utils import extract_classroom, parse_hnu_time


class WorkbookLoadError(ValueError):
    """Raised when an imported workbook is not a recognised course export."""


class SchedulerLogic:
    PALETTE = ("#F9C5D1", "#FDD9B5", "#FFF0B3", "#CDECCF", "#BDE8E9", "#C7DBF8", "#D8CCF2", "#F2CCE2")
    HEADER_ALIASES = {
        "course_id": ("课程编码",), "name": ("课程名称",), "teacher": ("授课教师",), "time": ("开课时间地点",),
        "target_class": ("开课班级",), "category": ("课程分类",), "credits": ("学分",), "notice_id": ("通知单号",),
    }

    def __init__(self) -> None:
        self.all_courses: list[Course] = []
        self.my_courses: list[Course] = []
        self.column_names: list[str] = []
        self.source_path: Path | None = None

    @staticmethod
    def _clean(value: object, fallback: str = "") -> str:
        return fallback if pd.isna(value) else str(value).strip()

    @staticmethod
    def _normalise_header(value: object) -> str:
        return str(value).replace("\n", " ").replace("\r", " ").strip()

    def _field(self, row: pd.Series, field: str, fallback: str = "") -> str:
        for header in self.HEADER_ALIASES[field]:
            if header in row.index:
                return self._clean(row[header], fallback)
        return fallback

    def get_color(self, value: str) -> str:
        digest = hashlib.blake2s(value.encode("utf-8"), digest_size=4).digest()
        return self.PALETTE[int.from_bytes(digest, "big") % len(self.PALETTE)]

    def load_excel(self, path: str | Path) -> int:
        """Load a workbook atomically so a failed import cannot erase current data."""
        source = Path(path)
        try:
            raw = pd.read_excel(source, header=None)
        except Exception as exc:
            raise WorkbookLoadError(f"无法读取文件：{exc}") from exc
        header_idx = next((index for index, row in raw.iterrows() if "课程名称" in {self._normalise_header(value) for value in row}), None)
        if header_idx is None:
            raise WorkbookLoadError("未找到“课程名称”表头，请选择学校导出的课程清单。")
        try:
            frame = pd.read_excel(source, header=header_idx)
        except Exception as exc:
            raise WorkbookLoadError(f"无法解析课程数据：{exc}") from exc
        frame.columns = [self._normalise_header(column) for column in frame.columns]
        missing = [name for name in ("课程名称", "开课时间地点") if name not in frame.columns]
        if missing:
            raise WorkbookLoadError(f"文件缺少必要字段：{'、'.join(missing)}")
        courses: list[Course] = []
        for index, row in frame.iterrows():
            name, raw_time = self._field(row, "name"), self._field(row, "time")
            slots = parse_hnu_time(raw_time)
            if not name:
                continue
            course_id = self._field(row, "course_id", "未编号")
            uid = f"{course_id}:{index}"
            courses.append(Course(uid=uid, course_id=course_id, name=name, teacher=self._field(row, "teacher", "未知"), slots=slots,
                full_data={column: self._clean(value) for column, value in row.items()}, raw_time=raw_time, color=self.get_color(uid),
                classroom=extract_classroom(raw_time), target_class=self._field(row, "target_class", "未知"),
                category=self._field(row, "category", "普通"), credits=self._field(row, "credits", "0"), notice_id=self._field(row, "notice_id", ""),
                source_row=header_idx + 2 + int(index)))
        self.all_courses, self.my_courses = courses, []
        self.column_names, self.source_path = list(frame.columns), source
        return len(courses)

    def filter_courses(self, keyword: str = "", day: int | None = None, period: int | None = None) -> list[Course]:
        return [course for course in self.all_courses if course.matches(keyword) and (day is None or period is None or course.has_slot(day, period))]

    def try_add(self, course: Course) -> tuple[bool, str]:
        if course in self.my_courses:
            return False, "该课程已在我的课表中。"
        if not course.slots:
            return False, "该课程尚未安排上课时间，无法加入课表。"
        conflicts = [existing.name for existing in self.my_courses if course.conflicts_with(existing)]
        if conflicts:
            return False, f"与“{'、'.join(conflicts)}”存在同周同节冲突。"
        self.my_courses.append(course)
        return True, "课程已加入课表。"

    def conflicts_with_current_schedule(self, course: Course) -> bool:
        return course in self.my_courses or any(course.conflicts_with(selected) for selected in self.my_courses)

    @staticmethod
    def _course_name_key(name: str) -> str:
        return "".join(str(name).split()).casefold()

    @staticmethod
    def _credit_value(value: object) -> Decimal:
        match = re.search(r"\d+(?:\.\d+)?", str(value or ""))
        if not match:
            return Decimal("0")
        try:
            return Decimal(match.group())
        except InvalidOperation:
            return Decimal("0")

    @staticmethod
    def _credit_course_key(course: Course) -> str:
        course_id = course.course_id.strip()
        return f"id:{course_id}" if course_id and course_id != "未编号" else f"name:{SchedulerLogic._course_name_key(course.name)}"

    @staticmethod
    def _teacher_keys(teachers: str) -> set[str]:
        text = re.sub(r"(?:副教授|教授|讲师|助教|老师)", "", str(teachers or ""))
        return {
            SchedulerLogic._course_name_key(name)
            for name in re.split(r"[,，、;；/\s]+", text)
            if name.strip() and name.strip() != "未知"
        }

    def calculate_total_credits(self, personal_courses: Iterable[tuple[str, str]] = ()) -> Decimal:
        """Sum unique catalogue courses represented by the current timetable."""
        total = Decimal("0")
        counted: set[str] = set()
        counted_names: set[str] = set()

        def add(course: Course) -> None:
            nonlocal total
            key = self._credit_course_key(course)
            name_key = self._course_name_key(course.name)
            if key not in counted and name_key not in counted_names:
                counted.add(key)
                counted_names.add(name_key)
                total += self._credit_value(course.credits)

        catalog_by_name: dict[str, list[Course]] = {}
        for course in self.all_courses:
            catalog_by_name.setdefault(self._course_name_key(course.name), []).append(course)

        personal_by_name: dict[str, set[str]] = {}
        for name, teacher in personal_courses:
            personal_by_name.setdefault(self._course_name_key(name), set()).update(self._teacher_keys(teacher))

        for name_key, teachers in personal_by_name.items():
            candidates = catalog_by_name.get(name_key, [])
            if not candidates:
                continue
            matched = max(
                candidates,
                key=lambda course: (
                    len(teachers & self._teacher_keys(course.teacher)),
                    self._teacher_keys(course.teacher) == teachers,
                    -len(self._teacher_keys(course.teacher) - teachers),
                ),
            )
            add(matched)

        for course in self.my_courses:
            add(course)
        return total

    def remove_course(self, course: Course) -> bool:
        if course not in self.my_courses:
            return False
        self.my_courses.remove(course)
        return True
