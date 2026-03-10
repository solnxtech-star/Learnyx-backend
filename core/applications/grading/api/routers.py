from django.conf import settings
from rest_framework.routers import DefaultRouter
from rest_framework.routers import SimpleRouter

from core.applications.grading.api.views.grade_student_views import (
    StudentProfileViewSet,
)

PREFIX = "grading"
API_VERSION = settings.API_VERSION

router = DefaultRouter() if settings.DEBUG else SimpleRouter()
router.register("students", StudentProfileViewSet, basename="students")


app_name = f"{PREFIX}"
urlpatterns = router.urls
