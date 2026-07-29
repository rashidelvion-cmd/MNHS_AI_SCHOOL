from django import forms

from academics.models import Subject, SchoolYear
from students.models import Student
from .models import Assessment, ScoreItem, QUARTER_CHOICES, COMPONENT_CHOICES


class ClassRecordSelectForm(forms.Form):
    student = forms.ModelChoiceField(queryset=Student.objects.all())
    subject = forms.ModelChoiceField(queryset=Subject.objects.all())
    school_year = forms.ModelChoiceField(queryset=SchoolYear.objects.all())
    quarter = forms.ChoiceField(choices=QUARTER_CHOICES, label="Quarter / Term")

    def clean(self):
        cleaned_data = super().clean()
        school_year = cleaned_data.get("school_year")
        quarter = cleaned_data.get("quarter")

        if school_year and quarter and int(quarter) > school_year.period_count:
            self.add_error(
                "quarter",
                f"{school_year} uses {school_year.get_grading_system_display()} — "
                f"only periods 1–{school_year.period_count} are valid.",
            )

        return cleaned_data


class ScoreItemForm(forms.ModelForm):
    class Meta:
        model = ScoreItem
        fields = ["component", "label", "raw_score", "highest_score"]

    def clean(self):
        cleaned_data = super().clean()
        raw_score = cleaned_data.get("raw_score")
        highest_score = cleaned_data.get("highest_score")

        if raw_score is not None and highest_score is not None:
            if highest_score <= 0:
                self.add_error("highest_score", "Highest possible score must be greater than 0.")
            elif raw_score > highest_score:
                self.add_error("raw_score", "Raw score cannot exceed the highest possible score.")

        return cleaned_data


class ECRSelectForm(forms.Form):
    """Pick a SubjectAssignment (teacher+subject+section+year) and period
    to open the official E-Class Record grid."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        from academics.models import SubjectAssignment

        self.fields["subject_assignment"] = forms.ModelChoiceField(
            queryset=SubjectAssignment.objects.select_related(
                "subject", "section", "teacher", "school_year"
            ).all(),
            label="Class (Subject - Section - Teacher)",
        )
        self.fields["quarter"] = forms.ChoiceField(
            choices=QUARTER_CHOICES, label="Quarter / Term"
        )

    def clean(self):
        cleaned_data = super().clean()
        assignment = cleaned_data.get("subject_assignment")
        quarter = cleaned_data.get("quarter")
        if assignment and quarter:
            school_year = assignment.school_year
            if int(quarter) > school_year.period_count:
                self.add_error(
                    "quarter",
                    f"{school_year} uses {school_year.get_grading_system_display()} — "
                    f"only periods 1–{school_year.period_count} are valid.",
                )
        return cleaned_data


class AssessmentForm(forms.ModelForm):
    """Add one graded column (assessment) to the E-Class Record."""

    class Meta:
        model = Assessment
        fields = ["component", "label", "highest_score", "competency"]
        labels = {
            "competency": "Learning Competency",
        }
        help_texts = {
            "competency": "Optional — skill or topic this assessment covers.",
        }
        widgets = {
            "competency": forms.TextInput(attrs={
                "placeholder": "e.g. Identifies the domain and range of a function",
                "class": "form-control",
            }),
        }

    def clean_highest_score(self):
        highest_score = self.cleaned_data["highest_score"]
        if highest_score <= 0:
            raise forms.ValidationError("Highest possible score must be greater than 0.")
        return highest_score
