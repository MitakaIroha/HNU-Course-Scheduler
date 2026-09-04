import unittest

from models import Course, DEFAULT_WEEKS, MAX_WEEK, MIN_WEEK, TimeSlot
from logic import SchedulerLogic
from parser_utils import parse_hnu_time, parse_weeks


def course(name, weeks, credits="0", course_id=None, teacher="Teacher"):
    return Course(
        uid=name,
        course_id=course_id or name,
        name=name,
        teacher=teacher,
        slots=(TimeSlot(1, frozenset({1, 2}), frozenset(weeks), ""),),
        full_data={},
        raw_time="",
        color="#FFFFFF",
        credits=credits,
    )


class ParserTests(unittest.TestCase):
    def test_parses_exported_schedule_line(self):
        slots = parse_hnu_time("1: A209 周一第0102节第(9-12)周")
        self.assertEqual(len(slots), 1)
        self.assertEqual(slots[0].weekday, 1)
        self.assertEqual(slots[0].periods, frozenset({1, 2}))
        self.assertEqual(slots[0].weeks, frozenset({9, 10, 11, 12}))

    def test_accepts_lists_and_ranges_of_weeks(self):
        self.assertEqual(parse_weeks("(1-2,4,6-7)周"), frozenset({1, 2, 4, 6, 7}))

    def test_week_boundaries_and_default_use_domain_constants(self):
        self.assertEqual(DEFAULT_WEEKS, frozenset(range(MIN_WEEK, MAX_WEEK + 1)))
        self.assertEqual(parse_weeks("第 1 周"), frozenset({MIN_WEEK}))
        self.assertEqual(parse_weeks("第 18 周"), frozenset({MAX_WEEK}))
        self.assertEqual(parse_weeks("1-18 周"), DEFAULT_WEEKS)

    def test_week_parser_rejects_out_of_range_values_and_ranges(self):
        self.assertEqual(parse_weeks("(18)周"), frozenset({MAX_WEEK}))
        for value in (
            "第 0 周", "第 19 周", "第 30 周", "(19)周", "(30)周", "(99)周",
            "0-18周", "1-30周", "19-20周", "19-30周",
        ):
            with self.subTest(value=value), self.assertRaises(ValueError):
                parse_weeks(value)
        self.assertEqual(parse_hnu_time("A209 周一第0102节第(19)周"), ())

    def test_time_slot_enforces_week_and_weekday_boundaries(self):
        TimeSlot(1, frozenset({1}), frozenset({MAX_WEEK}), "")
        with self.assertRaisesRegex(ValueError, "1 至 18"):
            TimeSlot(1, frozenset({1}), frozenset(), "")
        with self.assertRaisesRegex(ValueError, "1 至 18"):
            TimeSlot(1, frozenset({1}), frozenset({MAX_WEEK + 1}), "")
        with self.assertRaisesRegex(ValueError, "1 至 7"):
            TimeSlot(8, frozenset({1}), frozenset({1}), "")

    def test_rejects_course_periods_above_eleven(self):
        self.assertEqual(parse_hnu_time("1: A209 周一第1112节第(1-16)周"), ())
        with self.assertRaisesRegex(ValueError, "1 至 11"):
            TimeSlot(1, frozenset({12}), frozenset({1}), "")


class ConflictTests(unittest.TestCase):
    def test_courses_only_conflict_when_weeks_overlap(self):
        self.assertFalse(course("Odd", {1, 3}).conflicts_with(course("Even", {2, 4})))
        self.assertTrue(course("One", {1, 3}).conflicts_with(course("Other", {3, 4})))

    def test_availability_uses_courses_already_on_current_schedule(self):
        logic = SchedulerLogic()
        selected = course("Selected", {1, 3})
        logic.my_courses = [selected]
        self.assertTrue(logic.conflicts_with_current_schedule(selected))
        self.assertTrue(logic.conflicts_with_current_schedule(course("Conflict", {3, 5})))
        self.assertFalse(logic.conflicts_with_current_schedule(course("Available", {2, 4})))


class CatalogueTests(unittest.TestCase):
    def test_courses_without_scheduled_time_remain_searchable(self):
        logic = SchedulerLogic()
        unscheduled = Course(
            uid="英国小说",
            course_id="TW006WY24M",
            name="英国小说",
            teacher="刘远",
            slots=(),
            full_data={},
            raw_time="",
            color="#FFFFFF",
            credits="2",
        )
        logic.all_courses = [unscheduled]

        self.assertEqual([item.name for item in logic.filter_courses("英国小说")], ["英国小说"])
        self.assertEqual(logic.try_add(unscheduled)[1], "该课程尚未安排上课时间，无法加入课表。")


class CreditTests(unittest.TestCase):
    def test_total_credits_include_matched_personal_and_selected_courses(self):
        logic = SchedulerLogic()
        personal = course("高等数学 A I", {1}, "5", "MATH", "严子龙")
        selected = course("大学英语", {2}, "2.5", "ENG")
        logic.all_courses = [personal, selected]
        logic.my_courses = [selected]

        self.assertEqual(logic.calculate_total_credits([("高等数学AI", "严子龙教授")]), 7.5)

    def test_total_credits_do_not_count_same_course_twice(self):
        logic = SchedulerLogic()
        first = course("材料有机化学", {1}, "3.0", "CHEM", "教师甲")
        second = course("材料有机化学", {2}, "3.0", "OTHER-CHEM", "教师乙")
        logic.all_courses = [first, second]
        logic.my_courses = [second]

        self.assertEqual(logic.calculate_total_credits([("材料有机化学", "教师甲")]), 3)

    def test_credit_matching_prefers_the_complete_teacher_group(self):
        logic = SchedulerLogic()
        unrelated = course("软件工程导论", {1}, "3", "DZ215", "胡军")
        actual = course("软件工程导论", {2}, "4", "ZH129", "胡军,边耐政,金敏")
        logic.all_courses = [unrelated, actual]

        personal = [
            ("软件工程导论", "边耐政副教授,胡军副教授,金敏教授"),
            ("软件工程导论", "胡军副教授"),
        ]
        self.assertEqual(logic.calculate_total_credits(personal), 4)


if __name__ == "__main__":
    unittest.main()
