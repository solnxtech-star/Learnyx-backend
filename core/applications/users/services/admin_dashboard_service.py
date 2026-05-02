
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from django.db.models import Count
from django.db.models import Q

from core.applications.academics.models import AcademicTerm
from core.applications.academics.models import ClassRoom
from core.applications.academics.models import StudentSubjectEnrollment
from core.applications.academics.models import Subject
from core.applications.academics.models import TeachingAssignment
from core.applications.users.models import StudentProfile
from core.applications.users.models import TeacherProfile

logger = logging.getLogger(__name__)


class DashboardService:
    """
    Aggregates all data needed for the admin dashboard in a single
    database round-trip per section.

    Usage::

        service = DashboardService(school=request.user.school)
        data = service.get_dashboard_data()

    The returned dict matches the shape expected by ``DashboardSerializer``.
    """

    # Number of activity items to surface in the feed.
    ACTIVITY_FEED_LIMIT = 10

    def __init__(self, school) -> None:
        self.school = school


    def get_dashboard_data(self) -> dict[str, Any]:
        """
        Return the complete dashboard payload.

        All sections are computed independently; a failure in one section
        is logged and returns a safe default so the rest of the dashboard
        still renders.
        """
        return {
            "overview":            self._safe(self._get_overview),
            "current_term":        self._safe(self._get_current_term),
            "gender_distribution": self._safe(self._get_gender_distribution),
            "recent_activity":     self._safe(self._get_recent_activity),
        }

    # ──────────────────────────────────────────────────────────────────
    # Section: Academic Overview
    # ──────────────────────────────────────────────────────────────────

    def _get_overview(self) -> dict[str, int]:
        """
        Counts for the four top-level dashboard cards.

        Queries:
          • ClassRoom   — all classrooms belonging to this school
          • StudentProfile — approved students via user__school
          • Subject     — active subjects belonging to this school
          • TeacherProfile — approved teachers via user__school
        """
        active_classes = (
            ClassRoom.objects
            .for_school(self.school)
            .count()
        )

        total_students = (
            StudentProfile.objects
            .filter(user__school=self.school, status="APPROVED")
            .count()
        )

        total_subjects = (
            Subject.objects
            .for_school(self.school)
            .filter(is_active=True)
            .count()
        )

        total_teachers = (
            TeacherProfile.objects
            .filter(user__school=self.school, status="APPROVED")
            .count()
        )

        return {
            "active_classes": active_classes,
            "total_students": total_students,
            "total_subjects": total_subjects,
            "total_teachers": total_teachers,
        }



    def _get_current_term(self) -> dict | None:
        """
        Return the currently active term for this school.

        Resolution order:
          1. A term explicitly marked ``is_active=True`` inside an active session.
          2. The highest-numbered term inside the active session (fallback).
          3. None — shown as "No active term" on the dashboard.
        """
        base_qs = (
            AcademicTerm.objects
            .filter(session__school=self.school, session__is_active=True)
            .select_related("session")
        )

        term = (
            base_qs.filter(is_active=True).first()
            or base_qs.order_by("-term_number").first()
        )

        if term is None:
            return None

        return {
            "term_name":    term.get_term_display_name(),
            "session_name": term.session.name,
            "term_number":  term.term_number,
            "status":       "Open" if term.is_active else "Closed",
            "start_date":   term.start_date,
            "end_date":     term.end_date,
        }

    # ──────────────────────────────────────────────────────────────────
    # Section: Gender Distribution
    # ──────────────────────────────────────────────────────────────────

    def _get_gender_distribution(self) -> dict[str, float]:
        """
        Percentage breakdown of approved student genders.

        Returns a dict like::

            {"male": 65.0, "female": 35.0, "other": 0.0}

        Students with a blank / null gender field are grouped under "other".
        Percentages are rounded to one decimal place and always sum to 100.
        Returns an empty dict if there are no students.
        """
        qs = StudentProfile.objects.filter(
            user__school=self.school,
            status="APPROVED",
        )
        total = qs.count()

        if not total:
            return {}

        rows = (
            qs.values("gender")
            .annotate(count=Count("id"))
        )

        distribution: dict[str, float] = {}
        for row in rows:
            key = (row["gender"] or "other").lower().strip() or "other"
            distribution[key] = distribution.get(key, 0) + row["count"]

        # Convert raw counts → percentages
        return {
            key: round((count / total) * 100, 1)
            for key, count in distribution.items()
        }

    # ──────────────────────────────────────────────────────────────────
    # Section: Recent Activity
    # ──────────────────────────────────────────────────────────────────

    def _get_recent_activity(self) -> list[dict]:
        """
        Build a unified activity feed from multiple models, sorted by
        recency, capped at ``ACTIVITY_FEED_LIMIT`` items.

        Each item follows the shape::

            {
                "label":      str,       # Human-readable action name
                "identifier": str,       # Short code / name of the affected record
                "timestamp":  datetime,  # UTC datetime of the action
                "category":   str,       # Machine-readable type for icon mapping
            }

        To add a new activity source, append to the ``sources`` list below
        — no other changes required.
        """
        activities: list[dict] = []

        # ── Subject updates ──────────────────────────────────────────
        subject_qs = (
            Subject.objects
            .for_school(self.school)
            .filter(is_active=True)
            .order_by("-updated_at")
            .values("code", "updated_at")
            [:5]
        )
        for row in subject_qs:
            activities.append({
                "label":      "Subject Updated",
                "identifier": row["code"],
                "timestamp":  row["updated_at"],
                "category":   "subject",
            })

        # ── New terms ────────────────────────────────────────────────
        term_qs = (
            AcademicTerm.objects
            .filter(session__school=self.school)
            .select_related("session")
            .order_by("-created_at")
            [:3]
        )
        for term in term_qs:
            activities.append({
                "label":      "New Term Created",
                "identifier": f"{term.session.name} {term.get_term_display_name()}",
                "timestamp":  term.created_at,
                "category":   "term",
            })

        # ── Teaching assignments ─────────────────────────────────────
        assignment_qs = (
            TeachingAssignment.objects
            .filter(classroom__school=self.school)
            .select_related("classroom")
            .order_by("-created_at")
            .values("classroom__academic_class", "classroom__arm", "created_at")
            [:3]
        )
        for row in assignment_qs:
            identifier = (
                f"{row['classroom__academic_class']} {row['classroom__arm']}"
            )
            activities.append({
                "label":      "Course Assignment Locked",
                "identifier": identifier,
                "timestamp":  row["created_at"],
                "category":   "assignment",
            })

        # ── Subject enrollments ──────────────────────────────────────
        enrollment_qs = (
            StudentSubjectEnrollment.objects
            .filter(session__school=self.school)
            .select_related("subject")
            .order_by("-created_at")
            .values("subject__code", "created_at")
            [:3]
        )
        for row in enrollment_qs:
            activities.append({
                "label":      "Results Uploaded",
                "identifier": row["subject__code"],
                "timestamp":  row["created_at"],
                "category":   "result",
            })

        # ── Sort all sources by timestamp and cap ────────────────────
        activities.sort(key=lambda item: item["timestamp"], reverse=True)
        return activities[: self.ACTIVITY_FEED_LIMIT]

    # ──────────────────────────────────────────────────────────────────
    # Internal helpers
    # ──────────────────────────────────────────────────────────────────

    def _safe(self, fn, *, default=None):
        """
        Execute ``fn`` and return its result.

        If an exception is raised, log it and return ``default`` so that
        a single broken section never takes down the whole dashboard.
        """
        try:
            return fn()
        except Exception:
            logger.exception(
                "DashboardService: error in %s for school=%s",
                fn.__name__,
                getattr(self.school, "id", self.school),
            )
            return default
