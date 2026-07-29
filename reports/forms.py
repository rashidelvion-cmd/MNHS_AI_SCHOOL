from django import forms

from academics.models import GradeLevel, SchoolYear, Section
from students.models import Student


class Sf9SelectForm(forms.Form):
    student = forms.ModelChoiceField(queryset=Student.objects.none())
    school_year = forms.ModelChoiceField(queryset=SchoolYear.objects.all())

    def __init__(self, *args, student_queryset=None, **kwargs):
        super().__init__(*args, **kwargs)
        if student_queryset is not None:
            self.fields["student"].queryset = student_queryset


class SF1UploadForm(forms.Form):
    """Upload form for the SF1-SHS import. The three dropdowns are the
    authoritative destination; the file header is only cross-checked."""

    MAX_UPLOAD_BYTES = 10 * 1024 * 1024  # 10 MB

    school_year = forms.ModelChoiceField(
        queryset=SchoolYear.objects.all().order_by("-is_active", "-year"),
        label="School Year",
    )
    grade_level = forms.ModelChoiceField(
        queryset=GradeLevel.objects.all(),
        label="Grade Level",
    )
    section = forms.ModelChoiceField(
        queryset=Section.objects.select_related("grade_level").all(),
        label="Section",
    )
    file = forms.FileField(
        label="Official SF1-SHS file (.xlsx or .xls)",
        help_text="Upload the accomplished official SF1 School Register for Senior High School (2026 .xlsx or legacy 2018 .xls).",
    )
    semester = forms.ChoiceField(
        choices=[("1", "1st Semester"), ("2", "2nd Semester")],
        initial="1",
        label="Semester",
        help_text="SF1-SHS is issued per semester; recorded on the enrollments created.",
    )

    def clean_file(self):
        uploaded = self.cleaned_data["file"]
        name = (uploaded.name or "").lower()
        if not (name.endswith(".xlsx") or name.endswith(".xls")):
            raise forms.ValidationError(
                "Only .xlsx or .xls files are accepted — please upload the "
                "official SF1-SHS Excel file (not .xlsb or other formats)."
            )
        if uploaded.size and uploaded.size > self.MAX_UPLOAD_BYTES:
            raise forms.ValidationError("File is larger than 10 MB.")
        return uploaded

    def clean(self):
        cleaned = super().clean()
        section = cleaned.get("section")
        grade_level = cleaned.get("grade_level")
        if section and grade_level and section.grade_level_id != grade_level.pk:
            raise forms.ValidationError(
                "The selected section does not belong to the selected grade level."
            )
        return cleaned


class SF1ExportForm(forms.Form):
    """Selection form for generating the official SF1-SHS file."""

    school_year = forms.ModelChoiceField(
        queryset=SchoolYear.objects.all().order_by("-is_active", "-year"),
        label="School Year",
    )
    grade_level = forms.ModelChoiceField(
        queryset=GradeLevel.objects.all(),
        label="Grade Level",
    )
    section = forms.ModelChoiceField(
        queryset=Section.objects.select_related("grade_level").all(),
        label="Section",
    )
    semester = forms.ChoiceField(
        choices=[("1", "1st Semester"), ("2", "2nd Semester")],
        initial="1",
        label="Semester",
    )

    def clean(self):
        cleaned = super().clean()
        section = cleaned.get("section")
        grade_level = cleaned.get("grade_level")
        if section and grade_level and section.grade_level_id != grade_level.pk:
            raise forms.ValidationError(
                "The selected section does not belong to the selected grade level."
            )
        return cleaned


class SF2ExportForm(forms.Form):
    """Selection form for generating the official SF2-SHS file."""

    MONTH_CHOICES = [
        (1, "January"), (2, "February"), (3, "March"), (4, "April"),
        (5, "May"), (6, "June"), (7, "July"), (8, "August"),
        (9, "September"), (10, "October"), (11, "November"), (12, "December"),
    ]

    school_year = forms.ModelChoiceField(
        queryset=SchoolYear.objects.all().order_by("-is_active", "-year"),
        label="School Year",
    )
    grade_level = forms.ModelChoiceField(
        queryset=GradeLevel.objects.all(),
        label="Grade Level",
    )
    section = forms.ModelChoiceField(
        queryset=Section.objects.select_related("grade_level").all(),
        label="Section",
    )
    semester = forms.ChoiceField(
        choices=[("1", "1st Semester"), ("2", "2nd Semester")],
        initial="1",
        label="Semester",
    )
    month = forms.TypedChoiceField(
        choices=MONTH_CHOICES,
        coerce=int,
        label="Reporting Month",
    )
    year = forms.IntegerField(
        min_value=2000,
        max_value=2100,
        label="Year",
    )

    def clean(self):
        cleaned = super().clean()
        section = cleaned.get("section")
        grade_level = cleaned.get("grade_level")
        if section and grade_level and section.grade_level_id != grade_level.pk:
            raise forms.ValidationError(
                "The selected section does not belong to the selected grade level."
            )
        month = cleaned.get("month")
        year = cleaned.get("year")
        if month and year:
            import datetime
            today = datetime.date.today()
            if (year, month) > (today.year, today.month):
                raise forms.ValidationError(
                    "The reporting month cannot be in the future."
                )
        return cleaned


class SF9ExportForm(forms.Form):
    """
    Selection form for generating the official SF9-SHS Excel report card.

    The signature/transfer fields are optional free text written straight
    into the form's approval blocks — no schema is involved (the
    adviser-to-section link remains deferred).
    """

    student = forms.ModelChoiceField(queryset=Student.objects.none(), label="Learner")
    school_year = forms.ModelChoiceField(
        queryset=SchoolYear.objects.all().order_by("-is_active", "-year"),
        label="School Year",
    )

    adviser_name = forms.CharField(required=False, label="Class Adviser (name)")
    adviser_position = forms.CharField(
        required=False, label="Adviser position", initial="Teacher III"
    )
    principal_name = forms.CharField(required=False, label="Principal (name)")
    principal_position = forms.CharField(
        required=False, label="Principal position", initial="Principal I"
    )
    admitted_to_grade = forms.CharField(required=False, label="Admitted to Grade")
    eligible_for_admission_to_grade = forms.CharField(
        required=False, label="Eligible for Admission to Grade"
    )

    def __init__(self, *args, student_queryset=None, **kwargs):
        super().__init__(*args, **kwargs)
        if student_queryset is not None:
            self.fields["student"].queryset = student_queryset


class SF10ExportForm(forms.Form):
    """
    Selection form for generating the official SF10-SHS permanent record.

    The signature/date fields are optional free text written into the
    form's certification blocks — no schema is involved.
    """

    student = forms.ModelChoiceField(queryset=Student.objects.none(), label="Learner")
    grade_level = forms.ModelChoiceField(
        queryset=GradeLevel.objects.all(),
        label="Grade Level (11 = front page, 12 = back page)",
    )

    admission_date = forms.CharField(
        required=False, label="Date of SHS Admission (MM/DD/YYYY)"
    )
    adviser_name = forms.CharField(required=False, label="Adviser (printed name)")
    authorized_person = forms.CharField(
        required=False, label="Authorized person (printed name)"
    )
    date_checked = forms.CharField(required=False, label="Date Checked (MM/DD/YYYY)")

    def __init__(self, *args, student_queryset=None, **kwargs):
        super().__init__(*args, **kwargs)
        if student_queryset is not None:
            self.fields["student"].queryset = student_queryset
