from __future__ import annotations

import logging

from django.utils.decorators import method_decorator
from django.views.decorators.cache import cache_page
from django.views.decorators.vary import vary_on_headers
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.throttling import UserRateThrottle
from rest_framework.viewsets import ViewSet

from core.applications.users.api.schemas import admin_dashboard_schema
from core.applications.users.api.serializers.admin_dashboard_serializers import (
    DashboardSerializer,
)
from core.applications.users.services.admin_dashboard_service import DashboardService
from core.helper.permissions import IsPrincipalOrSchoolOwner

logger = logging.getLogger(__name__)




class DashboardRateThrottle(UserRateThrottle):
    """60 dashboard requests per minute per authenticated user."""

    rate = "60/min"



@method_decorator(cache_page(30), name="dispatch")
@method_decorator(vary_on_headers("Authorization"), name="dispatch")
class AdminDashboardView(ViewSet):
    """
    Admin dashboard summary.

    Exposes a single action:
        list()  →  GET /admin-dashboard/

    Registered via router.register() so no manual path() entry is needed.
    The ViewSet base class satisfies router.get_extra_actions() — unlike
    APIView which would raise AttributeError at startup.

    All data is scoped to the authenticated user's school (tenant).
    A 30-second server-side cache is applied per school to protect the
    database under high concurrent access.
    """

    permission_classes = [IsAuthenticated, IsPrincipalOrSchoolOwner]
    throttle_classes   = [DashboardRateThrottle]

    @admin_dashboard_schema
    def list(self, request: Request) -> Response:
        """
        Return the full dashboard payload for the authenticated admin's school.

        Delegates all aggregation to DashboardService so this method
        stays thin and independently testable.
        """
        school = getattr(request.user, "school", None)

        if school is None:
            logger.warning(
                "AdminDashboardView: user %s has no school assigned.",
                request.user.pk,
            )
            return Response(
                {"detail": "No school is associated with your account."},
                status=400,
            )

        logger.debug(
            "AdminDashboardView: serving dashboard — school=%s user=%s",
            school.pk,
            request.user.pk,
        )

        data       = DashboardService(school=school).get_dashboard_data()
        serializer = DashboardSerializer(data)
        return Response(serializer.data)
