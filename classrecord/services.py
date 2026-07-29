from decimal import Decimal, ROUND_HALF_UP

from .models import ScoreItem, SubjectWeighting, DEFAULT_WEIGHTS
from .transmutation import transmute

QUARTER_FIELD_MAP = {
    1: "first_quarter",
    2: "second_quarter",
    3: "third_quarter",
    4: "fourth_quarter",
}


def get_weights(subject):
    """Return {"WW": int, "PT": int, "QA": int} for a subject, falling back to DepEd defaults."""
    try:
        weighting = subject.subjectweighting
        return {
            "WW": weighting.written_work_weight,
            "PT": weighting.performance_task_weight,
            "QA": weighting.quarterly_assessment_weight,
        }
    except SubjectWeighting.DoesNotExist:
        return dict(DEFAULT_WEIGHTS)


def compute_grades(student, subject, school_year, quarter):
    """
    Full DepEd computation chain (DepEd Order No. 8, s. 2015) for one
    student, subject, school year and quarter/term.

    For each component (WW/PT/QA):
        Percentage Score = (sum raw / sum highest) * 100
        Weighted Score   = Percentage Score * component weight / 100

    Initial Grade  = sum of the three Weighted Scores (2 decimal places)
    Quarterly/Term Grade = TRANSMUTE(Initial Grade)   <- the official grade

    Returns (initial_grade_or_None, term_grade_or_None, breakdown).
    Both grades are None when no scores exist yet for the period.

    A component with no scores contributes 0 weighted points; a score item
    with highest_score = 0 is ignored (blank = not administered).
    """
    items = ScoreItem.objects.filter(
        student=student, subject=subject, school_year=school_year, quarter=quarter
    )
    weights = get_weights(subject)

    breakdown = {}
    total_weighted_score = Decimal("0")
    has_any_scores = False

    for component, weight in weights.items():
        component_items = [i for i in items if i.component == component]
        total_raw = sum((i.raw_score for i in component_items), Decimal("0"))
        total_highest = sum((i.highest_score for i in component_items), Decimal("0"))

        if total_highest > 0:
            has_any_scores = True
            percentage_score = (total_raw / total_highest) * Decimal("100")
        else:
            percentage_score = Decimal("0")

        weighted_score = percentage_score * Decimal(weight) / Decimal("100")
        total_weighted_score += weighted_score

        breakdown[component] = {
            "weight": weight,
            "total_raw": total_raw,
            "total_highest": total_highest,
            "percentage_score": percentage_score.quantize(Decimal("0.01")),
            "weighted_score": weighted_score.quantize(Decimal("0.01")),
            "items": component_items,
        }

    if not has_any_scores:
        return None, None, breakdown

    initial_grade = total_weighted_score.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    term_grade = transmute(initial_grade)
    return initial_grade, term_grade, breakdown


def compute_quarterly_grade(student, subject, school_year, quarter):
    """
    Backward-compatible wrapper used by the existing per-student Class
    Record pages: returns (term_grade, breakdown).

    The breakdown keeps its original shape (one entry per WW/PT/QA
    component) so existing callers/templates keep working unchanged.

    Note: the returned grade is now the official TRANSMUTED Quarterly/Term
    Grade (DO 8 s. 2015) rather than the rounded Initial Grade. Callers
    that also need the Initial Grade should use compute_grades().
    """
    _initial_grade, term_grade, breakdown = compute_grades(
        student, subject, school_year, quarter
    )
    return term_grade, breakdown


def sync_grade(student, subject, school_year, quarter):
    """
    Recompute the period from the E-Class Record and write the official
    transmuted Term Grade into the Grade record (auto-sync).

    Grade.save() recomputes the subject Final Grade from the periods that
    apply to the school year's grading system. Returns the term grade, or
    None when the period has no scores (the Grade record is left alone).
    """
    from grades.models import Grade

    _initial, term_grade, _breakdown = compute_grades(
        student, subject, school_year, quarter
    )
    if term_grade is None:
        return None

    grade, _created = Grade.objects.get_or_create(
        student=student, subject=subject, school_year=school_year
    )
    setattr(grade, QUARTER_FIELD_MAP[quarter], term_grade)
    grade.save()
    return term_grade
