from django.conf import settings
from rest_framework.routers import DefaultRouter
from rest_framework.routers import SimpleRouter

from core.applications.academics.api.views.accessment_entry_views import (
    AssessmentEntryViewSet,
)
from core.applications.academics.api.views.accessment_entry_views import (
    AssessmentRecordViewSet,
)
from core.applications.academics.api.views.accessment_entry_views import (
    BulkAssessmentEntryViewSet,
)
from core.applications.academics.api.views.teachers_dashboard_views import (
    TeacherDashboardViewSet,
)

PREFIX = "academics"

API_VERSION = settings.API_VERSION


if settings.DEBUG:
    router = DefaultRouter()
else:
    router = SimpleRouter()


router.register("accessment-entry", AssessmentEntryViewSet, basename="accessment-entry")
router.register(
    "accessment-record",
    AssessmentRecordViewSet,
    basename="accessment-record",
)
router.register(
    "bulk-accessment-entry",
    BulkAssessmentEntryViewSet,
    basename="bulk-accessment-entry",
)
router.register(
    "teachers-dashboard",
    TeacherDashboardViewSet,
    basename="teachers-dashboard",
)


app_name = f"{PREFIX}"
urlpatterns = router.urls
