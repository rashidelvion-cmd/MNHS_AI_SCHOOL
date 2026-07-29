from django import forms
from django.contrib.auth import get_user_model
from .models import Student


class StudentForm(forms.ModelForm):
    class Meta:
        model = Student
        fields = "__all__"
        widgets = {
            # Render photo with a clear label; ClearableFileInput is Django default for ImageField
            "photo": forms.ClearableFileInput(attrs={"accept": "image/*"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        User = get_user_model()

        if "user" in self.fields:
            self.fields["user"].queryset = User.objects.filter(role="student")
            self.fields["user"].required = False
            self.fields["user"].help_text = "Login account this student uses (role: Student)."

        if "guardians" in self.fields:
            self.fields["guardians"].queryset = User.objects.filter(role="parent")
            self.fields["guardians"].required = False
            self.fields["guardians"].help_text = "Parent/guardian account(s) allowed to view this student (role: Parent)."

        if "photo" in self.fields:
            self.fields["photo"].required = False
            self.fields["photo"].label = "Student Photo"
            self.fields["photo"].help_text = "Optional. Upload a clear photo of the student (JPEG or PNG recommended)."

        # Medical Information — D[055]
        # Q3-B: hide from student and parent roles.
        # Q2-A: not shown on the list page (handled by the template).
        # The request is not available here, so the view must exclude the
        # medical fields for restricted roles before passing the form.
        for field_name in ("medical_condition", "allergies", "blood_type"):
            if field_name in self.fields:
                self.fields[field_name].required = False

        if "medical_condition" in self.fields:
            self.fields["medical_condition"].label = "Medical Condition"
        if "allergies" in self.fields:
            self.fields["allergies"].label = "Allergies"
        if "blood_type" in self.fields:
            self.fields["blood_type"].label = "Blood Type"
            self.fields["blood_type"].widget.attrs["placeholder"] = "e.g. O+, A-, B+"