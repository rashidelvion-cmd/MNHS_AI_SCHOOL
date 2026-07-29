from django import forms
from .models import Attendance


class AttendanceForm(forms.ModelForm):

    class Meta:
        model = Attendance
        fields = "__all__"

class AttendanceMarkSelectForm(forms.Form):
    """Pick a section and date to open the bulk marking sheet."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Imported here to avoid changing this module's import surface for
        # existing code paths.
        from academics.models import SchoolYear, Section

        self.fields["school_year"] = forms.ModelChoiceField(
            queryset=SchoolYear.objects.all().order_by("-is_active", "-year"),
            label="School Year",
        )
        self.fields["section"] = forms.ModelChoiceField(
            queryset=Section.objects.select_related("grade_level").all(),
            label="Section",
        )
        self.fields["date"] = forms.DateField(
            label="Date",
            widget=forms.DateInput(attrs={"type": "date"}),
        )
