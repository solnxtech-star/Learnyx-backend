from django.conf import settings
from core.applications.academics.api.views.accessment_entry_views import AssessmentEntryViewSet, AssessmentRecordViewSet, BulkAssessmentEntryViewSet
from rest_framework.routers import DefaultRouter, SimpleRouter

PREFIX = "academics"

API_VERSION = settings.API_VERSION


if settings.DEBUG:
    router = DefaultRouter()
else:
    router = SimpleRouter()


router.register("accessment-entry", AssessmentEntryViewSet, basename="accessment-entry")
router.register("accessment-record", AssessmentRecordViewSet, basename="accessment-record")
router.register("bulk-accessment-entry", BulkAssessmentEntryViewSet, basename="bulk-accessment-entry")



app_name = f"{PREFIX}"
urlpatterns = router.urls
