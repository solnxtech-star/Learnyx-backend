from django.conf import settings
from rest_framework.routers import DefaultRouter
from rest_framework.routers import SimpleRouter

from core.applications.users.api.views.academic_views import AcademicSessionViewSet
from core.applications.users.api.views.academic_views import AcademicTermViewSet
from core.applications.users.api.views.academic_views import GenaralClassRoomViewSet
from core.applications.users.api.views.academic_views import SubjectViewSet
from core.applications.users.api.views.academic_views import TeacherViewSet
from core.applications.users.api.views.admin_accessment_views import (
    AssessmentPolicyViewSet,
)
from core.applications.users.api.views.admin_accessment_views import (
    AssessmentTypeViewSet,
)
from core.applications.users.api.views.admin_grading_views import AdminUsersViewset
from core.applications.users.api.views.admin_grading_views import ClassRoomViewSet
from core.applications.users.api.views.admin_grading_views import GradeScaleViewSet
from core.applications.users.api.views.views import UserViewSet

PREFIX = "users"
API_VERSION = settings.API_VERSION

if settings.DEBUG:
    router = DefaultRouter()
else:
    router = SimpleRouter()

# ====== FIXED ORDER: Most specific FIRST, generic LAST ======
# 1. Specific paths FIRST
router.register("classrooms", ClassRoomViewSet, basename="classrooms")
router.register("admin-users", AdminUsersViewset, basename="admin-users")
router.register(
    "academic-sessions", AcademicSessionViewSet, basename="academic-sessions"
)
router.register("academic-terms", AcademicTermViewSet, basename="academic-terms")
router.register("subjects", SubjectViewSet, basename="subjects")
router.register("teachers", TeacherViewSet, basename="teachers")
router.register("grade-scales", GradeScaleViewSet, basename="grade-scales")
router.register("accessment-policy", AssessmentPolicyViewSet, basename="accessment-policy" )
router.register("accessment-type", AssessmentTypeViewSet, basename="accessment-type")
router.register("general-classrooms", GenaralClassRoomViewSet, basename="general-classrooms")


# 2. Generic/catch-all path LAST
router.register("", UserViewSet, basename="users")
# =============================================================

app_name = f"{PREFIX}"
urlpatterns = router.urls
