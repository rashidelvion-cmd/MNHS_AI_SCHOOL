"""
Shared building blocks for DepEd School Form import services.

Everything in this module is form-agnostic and reusable by the SF1, SF2,
SF9 and SF10 modules:

- template geometry described as data (CellMap / RowBlock)
- safe cell readers + normalizers for the DepEd conventions
  (official name format, M/F sex, mm/dd/yyyy dates, placeholder rows)
- ParsedRow / ParseResult dataclasses (row number + warnings + errors)
- the six-state classification vocabulary and the field-level diff engine
- temp-file upload sessions (UUID token, cleanup)

Nothing in this module touches the database.
"""

from __future__ import annotations

import datetime
import re
import uuid
from dataclasses import dataclass, field
from pathlib import Path

from django.conf import settings

# ---------------------------------------------------------------------------
# Classification vocabulary (Requirement 1: six explicit states)
# ---------------------------------------------------------------------------

CREATED = "created"
UPDATED = "updated"
NO_CHANGE = "no_change"
ALREADY_ENROLLED = "already_enrolled"
CONFLICT = "conflict"
SKIPPED = "skipped"  # error rows + placeholder rows

STATUS_LABELS = {
    CREATED: "New",
    UPDATED: "Update",
    NO_CHANGE: "No change",
    ALREADY_ENROLLED: "Already enrolled",
    CONFLICT: "Conflict",
    SKIPPED: "Skipped",
}


# ---------------------------------------------------------------------------
# Template geometry as data
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class RowBlock:
    """A contiguous run of learner rows in a template (e.g. SF1 male block)."""

    label: str          # e.g. "M" / "F"
    first_row: int      # 1-based sheet row of the first learner line
    last_row: int       # inclusive


@dataclass(frozen=True)
class CellMap:
    """
    Field name -> anchor column letter for one learner row.

    Merged template cells must be read at their anchor (top-left) column;
    the map records only that anchor.
    """

    columns: dict  # {field_name: "A"}

    def read_row(self, worksheet, row_number):
        """Return {field_name: raw_cell_value} for one sheet row."""
        return {
            name: worksheet[f"{col}{row_number}"].value
            for name, col in self.columns.items()
        }


# ---------------------------------------------------------------------------
# Parse result containers
# ---------------------------------------------------------------------------

@dataclass
class ParsedRow:
    sheet_row: int
    block: str
    data: dict = field(default_factory=dict)
    warnings: list = field(default_factory=list)
    errors: list = field(default_factory=list)

    # Filled in by the classifier (importer side):
    status: str = ""
    enrollment_status: str = ""
    diff: list = field(default_factory=list)   # [(label, old, new, is_overwrite)]
    existing_pk: int | None = None

    @property
    def is_valid(self):
        return not self.errors


@dataclass
class ParseResult:
    header: dict = field(default_factory=dict)
    rows: list = field(default_factory=list)          # list[ParsedRow]
    file_warnings: list = field(default_factory=list)
    file_errors: list = field(default_factory=list)

    @property
    def valid_rows(self):
        return [r for r in self.rows if r.is_valid]

    @property
    def error_rows(self):
        return [r for r in self.rows if not r.is_valid]

    @property
    def is_importable(self):
        return not self.file_errors and bool(self.valid_rows)


# ---------------------------------------------------------------------------
# Normalizers (DepEd conventions shared by SF1/SF2/SF9/SF10)
# ---------------------------------------------------------------------------

_NAME_EXTENSION_TOKENS = {
    "JR", "JR.", "SR", "SR.",
    "II", "III", "IV", "V", "VI", "VII", "VIII", "IX", "X",
}


def clean_text(value):
    """Cell value -> stripped string ('' for None/whitespace)."""
    if value is None:
        return ""
    return str(value).strip()


def normalize_lrn(value):
    """
    Strip spaces/hyphens; return normalized LRN string ('' if empty).

    Legacy .xls registers store the LRN as a float, so cells arrive as
    e.g. '121708120002.0' — the trailing '.0' (and any pure-integer
    float form) is reduced to the plain digit string.
    """
    text = clean_text(value)
    text = re.sub(r"[\s\-]", "", text)
    match = re.fullmatch(r"(\d+)\.0+", text)
    if match:
        return match.group(1)
    return text


def lrn_looks_official(lrn):
    """Official LRNs are 12 digits. Non-conforming ones import with a warning."""
    return bool(re.fullmatch(r"\d{12}", lrn))


def split_official_name(raw):
    """
    Split the DepEd name format:
        "Last Name, First Name, Name Extension, Middle Name"

    Returns (last, first, extension, middle, warning_or_None).

    Real files are frequently entered with only two comma segments
    ("DIONERO, JAYRON FABROA") — in that case the extension is detected
    from a known token at the tail of segment 2 and the middle name is
    left blank with a warning so the adviser reviews it in the preview.
    """
    text = clean_text(raw)
    if not text:
        return "", "", "", "", None

    parts = [p.strip() for p in text.split(",")]
    parts = [p for p in parts if p != ""] or [text]

    if len(parts) >= 4:
        last, first, extension, middle = parts[0], parts[1], parts[2], ", ".join(parts[3:])
        if extension and extension.upper().rstrip(".") + "." not in _NAME_EXTENSION_TOKENS \
                and extension.upper() not in _NAME_EXTENSION_TOKENS:
            # Third segment isn't a recognizable extension -> treat as middle.
            middle = f"{extension} {middle}".strip()
            extension = ""
        return last, first, extension, middle, None

    if len(parts) == 3:
        last, second, third = parts
        if third.upper() in _NAME_EXTENSION_TOKENS:
            # "Last, First, Jr." (no middle)
            return last, second, third, "", None
        if second.upper() in _NAME_EXTENSION_TOKENS:
            # rare "Last, Jr., Middle" entry mistakes -> keep literal, warn
            return last, second, "", third, "Unusual name segments — please verify."
        # "Last, First Jr., Middle" — extension embedded in the first-name
        # segment; split it out so the official four-part format is restored.
        second_tokens = second.split()
        if len(second_tokens) >= 2 and second_tokens[-1].upper() in _NAME_EXTENSION_TOKENS:
            return last, " ".join(second_tokens[:-1]), second_tokens[-1], third, None
        return last, second, "", third, None

    if len(parts) == 2:
        last, rest = parts
        tokens = rest.split()
        extension = ""
        if len(tokens) >= 2 and tokens[-1].upper() in _NAME_EXTENSION_TOKENS:
            extension = tokens[-1]
            tokens = tokens[:-1]
        if len(tokens) >= 2:
            # Cannot know where the first name ends and the middle name
            # begins — take all as first name, warn.
            first = " ".join(tokens)
            return last, first, extension, "", (
                "Name has no explicit middle-name segment — imported as first "
                "name only; please verify."
            )
        return last, " ".join(tokens), extension, "", None

    # single segment — no comma at all
    return text, "", "", "", "Name is not in 'Last, First, Middle' format — please verify."


def normalize_sex(value, block_label=None):
    """
    Normalize an SF sex cell (M/F/Male/Female) to the model values
    'Male'/'Female'. Falls back to the row's male/female block when the
    cell is blank. Returns (value_or_'', warning_or_None).
    """
    text = clean_text(value).upper()
    mapped = {"M": "Male", "MALE": "Male", "F": "Female", "FEMALE": "Female"}.get(text, "")

    block_mapped = {"M": "Male", "F": "Female"}.get((block_label or "").upper(), "")

    if mapped:
        if block_mapped and mapped != block_mapped:
            return mapped, (
                f"Sex '{mapped}' contradicts the {block_mapped} block the row "
                "is placed in — the explicit value was used."
            )
        return mapped, None

    if block_mapped:
        return block_mapped, None

    return "", None


def normalize_date(value):
    """
    Accept real Excel dates (datetime/date) and mm/dd/yyyy or mm-dd-yyyy
    strings. Returns (date_or_None, error_or_None).
    """
    if value is None or clean_text(value) == "":
        return None, None
    if isinstance(value, datetime.datetime):
        return value.date(), None
    if isinstance(value, datetime.date):
        return value, None

    text = clean_text(value)
    for fmt in ("%m/%d/%Y", "%m-%d-%Y", "%m/%d/%y", "%Y-%m-%d"):
        try:
            return datetime.datetime.strptime(text, fmt).date(), None
        except ValueError:
            continue
    return None, f"Unrecognized date '{text}' (expected mm/dd/yyyy)."


def is_placeholder_lrn(lrn_value, counter):
    """
    Blank SF templates pre-print the row counter (1..40) in the LRN
    column. A cell equal to its own counter is a placeholder, not data.
    """
    text = clean_text(lrn_value)
    if text == "":
        return True
    try:
        return int(float(text)) == counter
    except (TypeError, ValueError):
        return False


# ---------------------------------------------------------------------------
# Field-level diff engine (Requirement 2)
# ---------------------------------------------------------------------------

def diff_fields(instance, incoming, field_labels):
    """
    Compare a model instance against incoming {field: value}.

    Update rule: only non-empty incoming values are applied, so only those
    can differ. Returns [(label, old, new, is_overwrite)] where
    is_overwrite=True means a non-empty old value is being replaced
    (rendered amber in the preview) as opposed to a blank being filled.
    """
    changes = []
    for field_name, label in field_labels.items():
        new = incoming.get(field_name, None)
        if new is None or new == "":
            continue
        old = getattr(instance, field_name)
        if isinstance(old, datetime.date) or isinstance(new, datetime.date):
            equal = old == new
        else:
            equal = clean_text(old) == clean_text(new)
        if not equal:
            old_display = old if old not in (None, "") else "—"
            changes.append((label, old_display, new, old not in (None, "")))
    return changes


# ---------------------------------------------------------------------------
# Upload sessions (temp files with single-use UUID tokens)
# ---------------------------------------------------------------------------

UPLOAD_SUBDIR = "sf_uploads"
SESSION_MAX_AGE = datetime.timedelta(hours=24)


def _upload_dir():
    path = Path(settings.MEDIA_ROOT) / UPLOAD_SUBDIR
    path.mkdir(parents=True, exist_ok=True)
    return path


def save_upload(django_file, prefix):
    """Store an uploaded file; returns the session token.

    The uploaded file's extension is preserved (.xlsx or .xls) so the
    parser can detect legacy .xls files. Unknown extensions fall back to
    .xlsx for backward compatibility.
    """
    cleanup_stale_uploads()
    token = uuid.uuid4()
    name = (getattr(django_file, "name", "") or "").lower()
    extension = ".xls" if name.endswith(".xls") else ".xlsx"
    target = _upload_dir() / f"{prefix}_{token}{extension}"
    with open(target, "wb") as out:
        for chunk in django_file.chunks():
            out.write(chunk)
    return token


def upload_path(token, prefix):
    """Path for a session token, or None if it no longer exists.

    Checks the known spreadsheet extensions so both .xlsx and .xls
    sessions resolve correctly.
    """
    for extension in (".xlsx", ".xls"):
        target = _upload_dir() / f"{prefix}_{token}{extension}"
        if target.exists():
            return target
    return None


def discard_upload(token, prefix):
    for extension in (".xlsx", ".xls"):
        target = _upload_dir() / f"{prefix}_{token}{extension}"
        try:
            target.unlink(missing_ok=True)
        except OSError:
            pass


def cleanup_stale_uploads():
    """Opportunistic removal of session files older than SESSION_MAX_AGE."""
    now = datetime.datetime.now()
    try:
        for item in _upload_dir().iterdir():
            try:
                age = now - datetime.datetime.fromtimestamp(item.stat().st_mtime)
                if age > SESSION_MAX_AGE:
                    item.unlink(missing_ok=True)
            except OSError:
                continue
    except OSError:
        pass


def split_simple_name(raw):
    """
    Split the legacy SF1 name format used by the 2018.2.1.1 register:

        "Last Name, First Name Middle Name"

    Here the comma separates only the last name from the rest; the first
    and middle names are space-separated within the second segment, and a
    name extension (Jr./III/etc.) may appear as the last token before the
    middle name or at the very end.

    Returns (last, first, extension, middle, warning_or_None).

    Because first vs middle cannot be delimited reliably, the convention
    (matching how DepEd prints these) is: the LAST token of the remainder
    is the middle name, everything before it is the first name. A one-token
    remainder is taken as the first name with a blank middle name.
    """
    text = clean_text(raw)
    if not text:
        return "", "", "", "", None

    if "," not in text:
        return text, "", "", "", (
            "Name is not in 'Last, First Middle' format — please verify."
        )

    last, _, remainder = text.partition(",")
    last = last.strip()
    tokens = remainder.split()

    extension_tokens = {
        "JR", "SR", "II", "III", "IV", "V", "VI", "VII", "VIII", "IX", "X"
    }
    extension = ""
    # An extension may sit at the very end of the remainder, or (commonly
    # in these registers) between the first and middle names, e.g.
    # "PARADO, ANTHONY JR. GAMBA" -> first ANTHONY, ext JR., middle GAMBA.
    for index, token in enumerate(tokens):
        if token.upper().rstrip(".") in extension_tokens:
            extension = token
            tokens.pop(index)
            break

    if not tokens:
        return last, "", extension, "", None
    if len(tokens) == 1:
        return last, tokens[0], extension, "", None

    # Last token = middle name; the rest = first name.
    middle = tokens[-1]
    first = " ".join(tokens[:-1])
    return last, first, extension, middle, None
