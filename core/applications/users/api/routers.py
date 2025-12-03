from django.conf import settings
from rest_framework.routers import DefaultRouter, SimpleRouter

from core.applications.users.api.views.admin_views import AdminUsersViewset, ClassRoomViewSet
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

# 2. Generic/catch-all path LAST
router.register("", UserViewSet, basename="users")
# =============================================================

app_name = f"{PREFIX}"
urlpatterns = router.urls
