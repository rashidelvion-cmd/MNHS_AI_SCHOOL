# MNHS AI School

Django-based school management system (students, teachers, enrollment, attendance, grades).

## Setup

1. Create and activate a virtual environment:
   ```
   python -m venv venv
   venv\Scripts\activate
   ```

2. Install dependencies:
   ```
   pip install -r requirements.txt
   ```

3. Create a `.env` file in the project root (copy `.env.example` and fill in real values):
   ```
   SECRET_KEY=your-secret-key
   DEBUG=True
   ALLOWED_HOSTS=localhost,127.0.0.1

   DB_NAME=mnhs_ai_school
   DB_USER=postgres
   DB_PASSWORD=your-db-password
   DB_HOST=localhost
   DB_PORT=5432
   ```
   Never commit `.env` — it's already excluded via `.gitignore`.

4. Create the PostgreSQL database (must exist before migrating):
   ```
   createdb mnhs_ai_school
   ```

5. Run migrations:
   ```
   python manage.py migrate
   ```

6. Create a superuser:
   ```
   python manage.py createsuperuser
   ```

7. Run the dev server:
   ```
   python manage.py runserver
   ```

## Apps

- `accounts` — custom user model + login/logout
- `students`, `teachers` — core CRUD entities
- `academics` — school years, grade levels, sections, subjects, teacher assignments
- `enrollment` — enrolling students into a school year/grade/section
- `attendance` — daily attendance records
- `grades` — quarterly grades per subject (final grade auto-computed as the average of the 4 quarters)
- `classrecord` — DepEd Written Work / Performance Task / Quarterly Assessment score entry; computes the Quarterly Grade and can push it into `grades.Grade`
- `reports` — SF9 report card PDF generation (`reports/sf9.py`, built with ReportLab)
- `dashboard` — landing page after login (shows live counts, not placeholder numbers)
- `core` — placeholder, not yet wired into `config/urls.py`

## Grading system: Quarter vs Term

`SchoolYear.grading_system` controls whether a given school year is graded
using the SHS-standard 4 quarters (Q1–Q4) or a 3-term system (matching the
school's own SF9 sample). Set this per school year in Django Admin. Grades,
Class Record, and the SF9 PDF all adapt automatically — period 4 simply
doesn't apply (and isn't shown) for a 3-term school year.

## Notes

- Deployment (production) settings still need `DEBUG=False`, a real `ALLOWED_HOSTS`, and `SECURE_*`/HSTS hardening — current config is dev-oriented.
- Role-based access control: admin/principal/teacher can add/edit/delete; student/parent accounts are view-only, scoped to their own record (`Student.user`) or their children (`Student.guardians`). See `accounts/decorators.py` and `accounts/scoping.py`.
- Two migrations (`students/migrations/0003_...` and `classrecord/migrations/0001_initial.py`) were written by hand in an environment without Django installed. Run `python manage.py makemigrations --check` before `migrate` to confirm they match your models exactly.
- Same caveat applies to `academics/migrations/0006_schoolyear_grading_system.py` and `grades/migrations/0003_alter_grade_quarters_nullable.py`, added for the Quarter/Term support.
- SF9 PDF: general average and Promoted/Retained status are computed from `Grade.final_grade` across all subjects for the school year, using a 75 passing mark. There's no `Track`/`Strand` field on `Student` yet, so it isn't shown on the report — add one if your SF9 needs it. School name/address come from `SCHOOL_NAME`/`SCHOOL_ADDRESS` in `.env`.
- No automated tests exist yet.
