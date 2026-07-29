"""
SF1-SHS format profiles.

Each profile declares one register layout as data: how to detect it, where
its header rows and learner blocks are, which column holds each field, and
which name-splitting convention it uses. Adding a new SF1 version is a new
profile here — the parser dispatches on these without version-specific
branches.

Profiles supported:
  * "2026"  — official SF1-SHS 2026 template, sheet "SHSF-1"
  * "2018"  — legacy SF1-SHS 2018.2.1.1, sheet "school_form_1_shs_ver2018*"
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ..base import RowBlock, clean_text, split_official_name, split_simple_name


@dataclass(frozen=True)
class SF1Profile:
    key: str
    sheet_name: str                       # exact sheet name, or "" to sniff
    sheet_name_prefix: str                 # startswith match (legacy versions)
    columns: dict                          # field -> column letter
    blocks: tuple                          # (RowBlock, ...)
    header_rows: dict                      # school_name_row / context_row / section_row
    header_max_col: int
    name_splitter: str                     # "official" | "simple"
    lrn_header_cell: str                   # e.g. "A18" — for structure detection
    name_header_cell: str                  # e.g. "C18"
    has_placeholder_counters: bool         # blank templates pre-number the LRN col

    def split_name(self, raw):
        if self.name_splitter == "simple":
            return split_simple_name(raw)
        return split_official_name(raw)


# --------------------------------------------------------------------------
# 2026 official template (sheet "SHSF-1")
# --------------------------------------------------------------------------
PROFILE_2026 = SF1Profile(
    key="2026",
    sheet_name="SHSF-1",
    sheet_name_prefix="",
    columns={
        "lrn": "A",
        "name": "C",
        "sex": "G",
        "birth_date": "H",
        "religious_affiliation": "L",
        "house_street": "M",
        "barangay": "N",
        "municipality": "R",
        "province": "U",
        "father_name": "W",
        "mother_maiden_name": "X",
        "guardian_name": "Z",
        "guardian_relationship": "AC",
        "contact_number": "AD",
        "remarks_code": "AE",
    },
    blocks=(
        RowBlock(label="M", first_row=11, last_row=50),
        RowBlock(label="F", first_row=52, last_row=91),
    ),
    header_rows={"school_name_row": 3, "context_row": 5, "section_row": 7},
    header_max_col=35,
    name_splitter="official",
    lrn_header_cell="A9",
    name_header_cell="C9",
    has_placeholder_counters=True,
)


# --------------------------------------------------------------------------
# Legacy 2018.2.1.1 register (sheet "school_form_1_shs_ver2018.2.1.1")
#
# Verified from the client's real .xls:
#   header  school row 5, context row 9, section row 16
#   headers LRN=A18, NAME=C18
#   MALE    rows 20-44   FEMALE rows 46-63   (no placeholder counters)
#   columns Sex=K Birth=L Religion=Q House=U Barangay=Z Muni=AE Prov=AG
#           Father=AK Mother=AP Guardian=AR GuardRel=AV Contact=AX Remarks=BC
#   (Learning Modality = BA — intentionally not mapped; no DB field for it)
# --------------------------------------------------------------------------
PROFILE_2018 = SF1Profile(
    key="2018",
    sheet_name="",
    sheet_name_prefix="school_form_1_shs_ver2018",
    columns={
        "lrn": "A",
        "name": "C",
        "sex": "K",
        "birth_date": "L",
        "religious_affiliation": "Q",
        "house_street": "U",
        "barangay": "Z",
        "municipality": "AE",
        "province": "AG",
        "father_name": "AK",
        "mother_maiden_name": "AP",
        "guardian_name": "AR",
        "guardian_relationship": "AV",
        "contact_number": "AX",
        "remarks_code": "BC",
    },
    blocks=(
        RowBlock(label="M", first_row=20, last_row=44),
        RowBlock(label="F", first_row=46, last_row=63),
    ),
    header_rows={"school_name_row": 5, "context_row": 9, "section_row": 16},
    header_max_col=55,
    name_splitter="simple",
    lrn_header_cell="A18",
    name_header_cell="C18",
    has_placeholder_counters=False,
)


ALL_PROFILES = (PROFILE_2026, PROFILE_2018)


def _cell_text(worksheet, coordinate):
    return clean_text(worksheet[coordinate].value).upper()


def detect_profile(workbook):
    """
    Pick the profile for a workbook by sheet name first, then by header
    signature (LRN/NAME anchor cells). Returns (profile, worksheet) or
    (None, None) if nothing matches.
    """
    sheet_names = workbook.sheetnames

    # 1) exact / prefix sheet-name match
    for profile in ALL_PROFILES:
        for name in sheet_names:
            if profile.sheet_name and name == profile.sheet_name:
                return profile, workbook[name]
            if profile.sheet_name_prefix and name.startswith(profile.sheet_name_prefix):
                return profile, workbook[name]

    # 2) header-signature match against every sheet
    for profile in ALL_PROFILES:
        for name in sheet_names:
            ws = workbook[name]
            lrn_ok = _cell_text(ws, profile.lrn_header_cell) == "LRN"
            name_ok = "NAME" in _cell_text(ws, profile.name_header_cell)
            if lrn_ok and name_ok:
                return profile, ws

    return None, None
