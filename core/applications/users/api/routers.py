from django.conf import settings
from rest_framework.routers import DefaultRouter
from rest_framework.routers import SimpleRouter

from core.applications.users.api.views.admin_views import AdminUsersViewset
from core.applications.users.api.views.admin_views import ClassRoomViewSet
from core.applications.users.api.views.views import UserViewSet

PREFIX = "users"

API_VERSION = settings.API_VERSION

if settings.DEBUG:
    router = DefaultRouter()
else:
    router = SimpleRouter()

router.register("", UserViewSet, basename="users")
router.register("admin-users", AdminUsersViewset, basename="admin-users")
router.register("classrooms", ClassRoomViewSet, basename="classrooms")


app_name = f"{PREFIX}"
urlpatterns = router.urls
