"""
Month -> SHSF-2 day-column mapping.

The official SF2-SHS grid pre-prints weekday letters (M T W TH F S) in
five week-groups across columns F..AQ. Each class day of the reporting
month must be written under the column whose week-group and weekday slot
match the calendar.

Week-group anchor columns (verified against the official template; some
columns are pair-merged — these are the anchors):

    week 1: F  H  I  J  K  L
    week 2: M  O  P  Q  R  S
    week 3: T  V  W  X  Z  AB
    week 4: AC AE AF AG AH AI
    week 5: AJ AK AM AN AO AQ

Slots within a group are Monday..Saturday. Sundays are never mapped.
Months whose class days span a sixth week overflow the form; those days
are reported back so the caller can warn.
"""

from __future__ import annotations

import calendar
import datetime

WEEK_GROUPS = [
    ["F", "H", "I", "J", "K", "L"],
    ["M", "O", "P", "Q", "R", "S"],
    ["T", "V", "W", "X", "Z", "AB"],
    ["AC", "AE", "AF", "AG", "AH", "AI"],
    ["AJ", "AK", "AM", "AN", "AO", "AQ"],
]

DATE_ROW = 10          # row where the day-of-month number is written
FIRST_LEARNER_MARK_ROW = 12


def month_dates(year, month):
    """All dates of the month, Mondays..Saturdays only (Sundays excluded)."""
    _, last_day = calendar.monthrange(year, month)
    return [
        datetime.date(year, month, day)
        for day in range(1, last_day + 1)
        if datetime.date(year, month, day).weekday() < 6  # 6 = Sunday
    ]


def map_dates_to_columns(dates):
    """
    Map dates (same month, Mon-Sat) to template columns.

    Week index is anchored to the Monday of the week containing the 1st of
    the month, matching how advisers fill the paper form: the first row of
    weekday letters is the calendar week of the 1st, even when the month
    starts midweek.

    Returns (mapping: {date: column}, overflow: [dates beyond week 5]).
    """
    if not dates:
        return {}, []

    first = min(dates)
    week_anchor = first - datetime.timedelta(days=first.weekday())

    mapping = {}
    overflow = []
    for date in sorted(dates):
        week_index = (date - week_anchor).days // 7
        weekday_slot = date.weekday()  # Monday=0 .. Saturday=5
        if week_index >= len(WEEK_GROUPS):
            overflow.append(date)
            continue
        mapping[date] = WEEK_GROUPS[week_index][weekday_slot]
    return mapping, overflow
