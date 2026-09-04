"""Parsers for the time-and-location notation used in HNU course exports."""

from __future__ import annotations

import re

from models import DEFAULT_WEEKS, MAX_WEEK, MIN_WEEK, TimeSlot

DAY_MAP = {"一": 1, "二": 2, "三": 3, "四": 4, "五": 5, "六": 6, "日": 7, "天": 7}


def parse_weeks(week_info: str) -> frozenset[int]:
    """Turn ``(1-2,4-16)周`` into explicit semester week numbers."""
    text = str(week_info or "").strip()
    if not text:
        return DEFAULT_WEEKS
    match = re.search(r"\(([^)]*)\)", text)
    if match:
        content = match.group(1)
    else:
        match = re.search(r"(?:第\s*)?([0-9][0-9,，、\s\-~至]*)\s*周", text)
        if not match:
            return DEFAULT_WEEKS
        content = match.group(1)
    content = re.sub(r"\s*([-~至])\s*", r"\1", content)
    weeks: set[int] = set()
    found_number = False
    for part in re.split(r"[,，、\s]+", content):
        if not part:
            continue
        range_match = re.fullmatch(r"(\d+)\s*[-~至]\s*(\d+)", part)
        if range_match:
            found_number = True
            start, end = map(int, range_match.groups())
            if start <= end:
                bounded_start = max(MIN_WEEK, start)
                bounded_end = min(MAX_WEEK, end)
                if bounded_start <= bounded_end:
                    weeks.update(range(bounded_start, bounded_end + 1))
        elif part.isdigit():
            found_number = True
            week = int(part)
            if not MIN_WEEK <= week <= MAX_WEEK:
                raise ValueError(f"课程周次必须在 {MIN_WEEK} 至 {MAX_WEEK} 之间")
            weeks.add(week)
    if found_number and not weeks:
        raise ValueError(f"课程周次必须在 {MIN_WEEK} 至 {MAX_WEEK} 之间")
    return frozenset(weeks) if weeks else DEFAULT_WEEKS


def parse_hnu_time(time_str: object) -> tuple[TimeSlot, ...]:
    """Parse every valid line, tolerating room numbers and export decorations."""
    if time_str is None or str(time_str).strip().lower() == "nan":
        return ()
    slots: list[TimeSlot] = []
    for line in str(time_str).replace("\r", "").split("\n"):
        day_match = re.search(r"周\s*([一二三四五六日天])", line)
        period_match = re.search(r"第\s*([0-9\s,，、]+)\s*节", line)
        if not day_match or not period_match:
            continue
        period_text = period_match.group(1).strip()
        if re.search(r"[\s,，、]", period_text):
            parsed_periods = (int(value) for value in re.findall(r"\d+", period_text))
        else:
            parsed_periods = (int(period_text[index:index + 2]) for index in range(0, len(period_text), 2))
        parsed_periods = tuple(parsed_periods)
        if not parsed_periods or not all(1 <= period <= 11 for period in parsed_periods):
            continue
        periods = frozenset(parsed_periods)
        week_match = re.search(r"第?\s*(\([^)]*\)\s*周?)", line)
        raw_weeks = week_match.group(1).replace(" ", "") if week_match else ""
        try:
            weeks = parse_weeks(raw_weeks)
        except ValueError:
            continue
        slots.append(TimeSlot(DAY_MAP[day_match.group(1)], periods, weeks, raw_weeks))
    return tuple(slots)


def extract_classroom(time_str: object) -> str:
    """Extract the location preceding the weekday part of the first schedule line."""
    for line in str(time_str or "").splitlines():
        prefix = re.split(r"周\s*[一二三四五六日天]", line, maxsplit=1)[0]
        prefix = re.sub(r"^\s*\d+\s*[:：]\s*", "", prefix).strip()
        if prefix:
            return prefix
    return "未知"
