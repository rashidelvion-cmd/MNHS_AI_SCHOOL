"""
DepEd transmutation of the Initial Grade into the Quarterly/Term Grade,
per DepEd Order No. 8, s. 2015 (Appendix B).

Bands: 100 maps to 100; from 60.00 upward the bands are 1.60 wide and
map to 75..99; below 60.00 the bands are 4.00 wide and map down to 60.

Also provides the official descriptors (Appendix A) and pass/fail
remarks used by the report card and General Average displays.
"""

from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP

PASSING_GRADE = 75


def transmute(initial_grade):
    """
    Initial Grade (number/Decimal, 0..100) -> transmuted whole-number
    Quarterly/Term Grade per the official table. Returns None for None.
    """
    if initial_grade is None:
        return None

    value = Decimal(str(initial_grade))
    if value >= Decimal("100"):
        return 100
    if value >= Decimal("60"):
        # 60.00-61.59 -> 75, 61.60-63.19 -> 76, ... 98.40-99.99 -> 99
        steps = int((value - Decimal("60")) / Decimal("1.6"))
        return min(75 + steps, 99)
    if value >= Decimal("4"):
        # 4.00-7.99 -> 61, 8.00-11.99 -> 62, ... 56.00-59.99 -> 74
        steps = int((value - Decimal("4")) / Decimal("4"))
        return 61 + steps
    return 60


def descriptor(grade):
    """Official descriptor for a whole-number grade (Appendix A)."""
    if grade is None:
        return ""
    grade = int(Decimal(str(grade)).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
    if grade >= 90:
        return "Outstanding"
    if grade >= 85:
        return "Very Satisfactory"
    if grade >= 80:
        return "Satisfactory"
    if grade >= 75:
        return "Fairly Satisfactory"
    return "Did Not Meet Expectations"


def remarks(grade):
    if grade is None:
        return ""
    return "Passed" if Decimal(str(grade)) >= PASSING_GRADE else "Failed"


def round_whole(value):
    """DepEd display rounding: half-up to a whole number (None-safe)."""
    if value is None:
        return None
    return int(Decimal(str(value)).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
