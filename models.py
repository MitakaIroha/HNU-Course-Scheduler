"""Core domain models for the course scheduler."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping

MIN_WEEK = 1
MAX_WEEK = 18
DEFAULT_WEEKS = frozenset(range(MIN_WEEK, MAX_WEEK + 1))


@dataclass(frozen=True, slots=True)
class TimeSlot:
    """One recurring teaching slot in a semester."""

    weekday: int
    periods: frozenset[int]
    weeks: frozenset[int]
    raw_weeks: str = ""

    def __post_init__(self) -> None:
        if isinstance(self.weekday, bool) or not isinstance(self.weekday, int) or not 1 <= self.weekday <= 7:
            raise ValueError("星期必须在 1 至 7 之间")
        if not self.periods or not all(
            isinstance(period, int) and not isinstance(period, bool) and 1 <= period <= 11
            for period in self.periods
        ):
            raise ValueError("课程节次必须在 1 至 11 之间")
        if not self.weeks or not all(
            isinstance(week, int) and not isinstance(week, bool) and MIN_WEEK <= week <= MAX_WEEK
            for week in self.weeks
        ):
            raise ValueError(f"课程周次必须在 {MIN_WEEK} 至 {MAX_WEEK} 之间")

    def overlaps(self, other: "TimeSlot") -> bool:
        return self.weekday == other.weekday and bool(self.periods & other.periods) and bool(self.weeks & other.weeks)


@dataclass(slots=True)
class Course:
    """A course section imported from the school's workbook."""

    course_id: str
    name: str
    teacher: str
    slots: tuple[TimeSlot, ...]
    full_data: Mapping[str, str]
    raw_time: str
    color: str
    classroom: str = "未知"
    target_class: str = "未知"
    category: str = "普通"
    credits: str = "0"
    notice_id: str = ""
    uid: str = field(default="")
    source_row: int = 0

    def matches(self, keyword: str) -> bool:
        needle = keyword.casefold().strip()
        return not needle or any(needle in str(value).casefold() for value in (*self.full_data.values(), self.name, self.teacher, self.classroom))

    def has_slot(self, weekday: int, period: int, week: int | None = None) -> bool:
        return any(slot.weekday == weekday and period in slot.periods and (week is None or week in slot.weeks) for slot in self.slots)

    def conflicts_with(self, other: "Course") -> bool:
        return any(left.overlaps(right) for left in self.slots for right in other.slots)

    @property
    def week_summary(self) -> str:
        return "、".join(slot.raw_weeks or "全学期" for slot in self.slots)
