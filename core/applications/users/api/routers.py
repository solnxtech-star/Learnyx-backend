from django.conf import settings
from core.applications.users.api.views.admin_accessment_views import AssessmentPolicyViewSet, AssessmentTypeViewSet
from rest_framework.routers import DefaultRouter, SimpleRouter


from core.applications.users.api.views.academic_views import (
    AcademicSessionViewSet,
    AcademicTermViewSet,
    SubjectViewSet,
    TeacherViewSet,
)
from core.applications.users.api.views.admin_grading_views import (
    AdminUsersViewset,
    ClassRoomViewSet,
    GradeScaleViewSet,
)

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


# 2. Generic/catch-all path LAST
router.register("", UserViewSet, basename="users")
# =============================================================

app_name = f"{PREFIX}"
urlpatterns = router.urls
