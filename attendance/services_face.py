"""
attendance/services_face.py — Face Recognition Attendance service.

Client requirement (Messenger 4 Jul, Mhar):
    "with integration of IOT which is the Face Recognition on the attendance part"
    "Mobile Cam only"

Implementation: OpenCV LBPH (Q1-A) — no new dependencies.
    cv2.CascadeClassifier  — Haar cascade face detector (ships with OpenCV)
    cv2.face.LBPHFaceRecognizer_create() — Local Binary Pattern Histogram recogniser

Approved decisions:
    Q1-A  OpenCV LBPH — zero new installs
    Q2    Confidence < 100 = recognised (lower = better match)
    Q5    Date = today (automatic, no session date)
"""

from __future__ import annotations

import io
import logging
import os
import pickle
from typing import Optional

import cv2
import numpy as np
from PIL import Image as PILImage

logger = logging.getLogger(__name__)

# ── Tunable constants ─────────────────────────────────────────────────────────

CONFIDENCE_THRESHOLD = 100   # Q2: < 100 = recognised. Adjust here if needed.
FACE_MIN_SIZE        = (30, 30)   # Minimum face region in pixels
CASCADE_PATH         = cv2.data.haarcascades + "haarcascade_frontalface_default.xml"


# ── Face detector (shared, lazy-loaded) ──────────────────────────────────────

_cascade: Optional[cv2.CascadeClassifier] = None


def _get_cascade() -> cv2.CascadeClassifier:
    global _cascade
    if _cascade is None:
        _cascade = cv2.CascadeClassifier(CASCADE_PATH)
        if _cascade.empty():
            raise RuntimeError(
                f"Haar cascade not found at {CASCADE_PATH}. "
                "Ensure opencv-contrib-python is installed."
            )
    return _cascade


# ── Internal helpers ──────────────────────────────────────────────────────────

def _pil_to_gray(img: PILImage.Image, size: tuple = (200, 200)) -> np.ndarray:
    """Convert a PIL Image to a normalised grayscale numpy array."""
    img = img.convert("L").resize(size, PILImage.LANCZOS)
    return np.array(img, dtype=np.uint8)


def _detect_face(gray: np.ndarray) -> Optional[np.ndarray]:
    """
    Run Haar cascade on a grayscale image.
    Returns the largest detected face region as a 200×200 array, or None.
    """
    cascade = _get_cascade()
    faces = cascade.detectMultiScale(
        gray,
        scaleFactor=1.1,
        minNeighbors=5,
        minSize=FACE_MIN_SIZE,
    )
    if len(faces) == 0:
        return None
    # Use the largest detected face
    x, y, w, h = max(faces, key=lambda f: f[2] * f[3])
    face_region = gray[y:y + h, x:x + w]
    return cv2.resize(face_region, (200, 200))


# ── Public API ────────────────────────────────────────────────────────────────

def train_model(students) -> dict:
    """
    Train the LBPH model on all students who have a reference photo.
    Creates or updates a FaceEncoding record per student.

    Called by the face_train view (admin / ict_coordinator / principal — Q4).

    Returns:
        {
            "trained":  [list of student names trained],
            "skipped":  [list of student names without a photo],
            "errors":   [list of (name, error_message)],
        }
    """
    from .models import FaceEncoding

    trained, skipped, errors = [], [], []

    for student in students:
        name = f"{student.last_name}, {student.first_name}"
        if not student.photo:
            skipped.append(name)
            continue

        photo_path = student.photo.path
        if not os.path.exists(photo_path):
            errors.append((name, f"Photo file missing: {photo_path}"))
            continue

        try:
            pil_img = PILImage.open(photo_path)
            gray    = _pil_to_gray(pil_img)
            face    = _detect_face(gray)

            if face is None:
                # No face detected in the reference photo — train on the full
                # resized image as a fallback so the student is still in the model
                face = gray
                logger.warning(
                    "No face detected in reference photo for %s — "
                    "using full image as fallback.", name
                )

            # Train a single-sample LBPH recogniser for this student
            # and store the histogram data as a pickle blob
            recogniser = cv2.face.LBPHFaceRecognizer_create()
            recogniser.train([face], np.array([student.pk]))

            # Extract the histogram list (serialisable)
            hist_data = recogniser.getHistograms()
            blob = pickle.dumps({
                "student_pk":  student.pk,
                "histograms":  hist_data,
            })

            FaceEncoding.objects.update_or_create(
                student=student,
                defaults={
                    "encoding":     blob,
                    "source_photo": student.photo.name,
                },
            )
            trained.append(name)

        except Exception as exc:
            logger.exception("Error training face for %s", name)
            errors.append((name, str(exc)))

    return {"trained": trained, "skipped": skipped, "errors": errors}


def recognise_face(
    frame_bytes: bytes,
    section_student_ids: list[int],
) -> dict:
    """
    Attempt to recognise a face in a JPEG/PNG camera frame.

    Parameters:
        frame_bytes         — raw image bytes from the browser (base64-decoded)
        section_student_ids — PKs of students enrolled in the current section;
                              only match against these students

    Returns:
        {
            "success":     bool,
            "student_pk":  int | None,
            "student_name": str | None,
            "confidence":  float | None,
            "face_detected": bool,
            "message":     str,
        }
    """
    from .models import FaceEncoding

    # ── Decode frame ─────────────────────────────────────────────────────────
    try:
        pil_img = PILImage.open(io.BytesIO(frame_bytes))
        gray    = _pil_to_gray(pil_img)
    except Exception as exc:
        return {
            "success": False, "student_pk": None, "student_name": None,
            "confidence": None, "face_detected": False,
            "message": f"Could not decode frame: {exc}",
        }

    # ── Detect face ───────────────────────────────────────────────────────────
    face = _detect_face(gray)
    if face is None:
        return {
            "success": False, "student_pk": None, "student_name": None,
            "confidence": None, "face_detected": False,
            "message": "No face detected in frame.",
        }

    # ── Load encodings for this section's students ────────────────────────────
    encodings = FaceEncoding.objects.filter(
        student_id__in=section_student_ids
    ).select_related("student")

    if not encodings.exists():
        return {
            "success": False, "student_pk": None, "student_name": None,
            "confidence": None, "face_detected": True,
            "message": "No face encodings trained for this section. "
                       "Ask an admin to run Train Model first.",
        }

    # ── Build combined recogniser from stored histograms ─────────────────────
    recogniser = cv2.face.LBPHFaceRecognizer_create()
    all_hists, all_labels = [], []
    pk_to_encoding = {}

    for enc in encodings:
        try:
            data = pickle.loads(bytes(enc.encoding))
            for hist in data["histograms"]:
                all_hists.append(hist)
                all_labels.append(enc.student.pk)
            pk_to_encoding[enc.student.pk] = enc
        except Exception:
            logger.exception("Failed to deserialise encoding for %s", enc.student)

    if not all_hists:
        return {
            "success": False, "student_pk": None, "student_name": None,
            "confidence": None, "face_detected": True,
            "message": "Stored encodings could not be loaded. Please retrain.",
        }

    recogniser.train(all_hists, np.array(all_labels, dtype=np.int32))

    # ── Predict ───────────────────────────────────────────────────────────────
    predicted_pk, confidence = recogniser.predict(face)

    if confidence >= CONFIDENCE_THRESHOLD:
        return {
            "success": False, "student_pk": None, "student_name": None,
            "confidence": round(confidence, 1), "face_detected": True,
            "message": f"Face detected but not recognised (confidence {confidence:.1f}).",
        }

    # ── Recognised ────────────────────────────────────────────────────────────
    student = pk_to_encoding[predicted_pk].student
    return {
        "success":      True,
        "student_pk":   student.pk,
        "student_name": f"{student.last_name}, {student.first_name}",
        "confidence":   round(confidence, 1),
        "face_detected": True,
        "message":      f"Recognised: {student.last_name}, {student.first_name} "
                        f"(confidence {confidence:.1f})",
    }
