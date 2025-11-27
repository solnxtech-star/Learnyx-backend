import uuid
import contextlib
from typing import Literal

from django.contrib.auth import authenticate
from django.contrib.auth import user_logged_in
from django.contrib.auth.models import update_last_login
from django.contrib.auth.password_validation import validate_password
from django.core import exceptions as django_exceptions
from djoser.compat import get_user_email
from djoser.conf import settings
from djoser.serializers import UserCreateSerializer
from rest_framework import serializers
from rest_framework.exceptions import AuthenticationFailed
from rest_framework.exceptions import PermissionDenied
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from rest_framework_simplejwt.settings import api_settings
from django.db import transaction
from math import radians, cos, sin, asin, sqrt
from core.applications.academics.models import ClassRoom


from core.applications.users.models import (
    AdminProfile,
    School,
    StudentProfile,
    TeacherProfile,
    User,
)
from core.applications.users.token import default_token_generator
from core.helper.custom_exceptions import CustomError
from core.helper.enums import (
    AcademicClass,
    AdminType,
    AdmissionStatus,
    Gender,
    UserRole,
)
from core.helper.interface import BaseModelNoDefs


class CustomUserSerializer(serializers.ModelSerializer):
    """Serializer for listing or basic user details."""

    role_display = serializers.CharField(source="get_role_display", read_only=True)
    status_display = serializers.CharField(source="get_status_display", read_only=True)

    class Meta:
        model = User
        fields = [
            "id",
            "name",
            "email",
            "phone_number",
            "role",
            "role_display",
            "status_display",
            "is_active",
            "is_verified",
            "date_joined",
            "last_login",
        ]
        read_only_fields = [
            "id",
            "date_joined",
            "last_login",
            "role_display",
            "status_display",
        ]


class BaseRoleCreateSerializer(UserCreateSerializer):
    """
    Base serializer for all user-role registrations.
    Handles:
    - Password confirmation
    - Extracting profile fields safely
    - Assigning school for Student/Teacher/Admin
    - Dynamic profile creation
    """

    re_password = serializers.CharField(write_only=True, required=True)

    # To be overridden by subclasses
    role = None
    profile_model = None
    profile_fields = []

    # Not User model fields
    school_code = serializers.CharField(write_only=True, required=False)
    school_id = serializers.UUIDField(write_only=True, required=False)

    class Meta(UserCreateSerializer.Meta):
        model = User
        fields = UserCreateSerializer.Meta.fields + (
            "re_password",
            "school_code",
            "school_id",
        )
        extra_kwargs = {
            "password": {"write_only": True},
            "re_password": {"write_only": True},
        }

    # ---------------------------------------
    # VALIDATION
    # ---------------------------------------
    def validate(self, attrs):
        # 1. Password confirmation
        re_password = attrs.pop("re_password", None)
        if not re_password:
            raise CustomError.BadRequest({"re_password": "This field is required."})
        self._re_password = re_password

        # 2. Extract profile fields before parent validation
        extracted = {}
        for field in self.profile_fields:
            if field in attrs:
                extracted[field] = attrs.pop(field)
        self._profile_data = {k: v for k, v in extracted.items() if v not in ("", None)}

        # 3. Extract school values
        self._school_code = attrs.pop("school_code", None)
        self._school_id = attrs.pop("school_id", None)

        # 4. Run Djoser's validation (email uniqueness, password rules, etc.)
        attrs = super().validate(attrs)

        # 5. Confirm passwords match
        if attrs["password"] != self._re_password:
            raise CustomError.BadRequest({"re_password": "Passwords do not match."})

        return attrs

    # ---------------------------------------
    # CREATE USER + SCHOOL + PROFILE
    # ---------------------------------------
    @transaction.atomic
    def create(self, validated_data):
        # 1. Create user via Djoser
        user = super().create(validated_data)
        user.role = self.role

        # -----------------------------------
        # SCHOOL ASSIGNMENT LOGIC
        # -----------------------------------
        if self.role in [UserRole.STUDENT, UserRole.TEACHER]:
            if not self._school_code:
                raise CustomError.BadRequest({"school_code": "This field is required."})

            school = School.objects.filter(school_code=self._school_code).first()
            if not school:
                raise CustomError.NotFound({"school_code": "Invalid school_code."})

            user.school = school

            # optional status field
            if hasattr(user, "status"):
                user.status = AdmissionStatus.PENDING

        elif self.role == UserRole.ADMIN:
            # Super Admin assigns via school_id
            if self._school_id:
                school = School.objects.filter(id=self._school_id).first()
                if not school:
                    raise CustomError.NotFound({"school_id": "Invalid school_id"})
                user.school = school

            # Regular admin via school_code
            elif self._school_code:
                school = School.objects.filter(school_code=self._school_code).first()
                if not school:
                    raise CustomError.NotFound({"school_code": "Invalid school_code"})
                user.school = school

            else:
                raise CustomError.BadRequest(
                    {
                        "school": "Provide either school_id (owner) or school_code (admin)."
                    }
                )

        # Save user fields
        update_fields = ["role"]
        if user.school:
            update_fields.append("school")
        if hasattr(user, "status"):
            update_fields.append("status")

        user.save(update_fields=list(set(update_fields)))

        # ---------------------------------------
        # PROFILE CREATION
        # ---------------------------------------
        if self.profile_model:
            profile_data = dict(self._profile_data)

            # ---- Handle classroom assignment ----
            classroom_id = profile_data.pop("classroom_id", None)
            if classroom_id:
                classroom = ClassRoom.objects.filter(id=classroom_id).first()
                if not classroom:
                    raise CustomError.NotFound({"classroom_id": "Invalid classroom_id"})
                profile_data["classroom"] = classroom

            # Auto-generate staff ID for teachers
            if (
                self.profile_model.__name__ == "TeacherProfile"
                and not profile_data.get("staff_id")
            ):
                profile_data["staff_id"] = f"STF-{uuid.uuid4().hex[:8].upper()}"

            # StudentProfile auto generates student_id in model.save()
            self.profile_model.objects.create(user=user, **profile_data)

        return user


class CustomUserCreateSerializer(BaseRoleCreateSerializer):
    """
    Student signup serializer.
    Adds academic fields and classroom assignment.
    """
    role = UserRole.STUDENT
    profile_model = StudentProfile

    profile_fields = [
        "gender",
        "current_class",
        "guardian_name",
        "guardian_phone",
        "address",
        "classroom_id",
    ]

    gender = serializers.ChoiceField(choices=Gender.choices, required=False)
    current_class = serializers.ChoiceField(
        choices=AcademicClass.choices, required=False
    )
    guardian_name = serializers.CharField(required=False, allow_blank=True)
    guardian_phone = serializers.CharField(required=False, allow_blank=True)
    address = serializers.CharField(required=False, allow_blank=True)

    classroom_id = serializers.CharField(write_only=True, required=False, allow_blank=True)


    school_code = serializers.CharField(write_only=True, required=True)

    class Meta(BaseRoleCreateSerializer.Meta):
        fields = BaseRoleCreateSerializer.Meta.fields + (
            "gender",
            "current_class",
            "guardian_name",
            "guardian_phone",
            "address",
            "classroom_id",
        )



class CustomTeacherCreateSerializer(BaseRoleCreateSerializer):
    role = UserRole.TEACHER
    profile_model = TeacherProfile

    profile_fields = [
        "qualification",
        "specialization",
        "department",
        "staff_id",
    ]

    qualification = serializers.CharField(required=False, allow_blank=True)
    specialization = serializers.CharField(required=False, allow_blank=True)
    department = serializers.CharField(required=False, allow_blank=True)
    staff_id = serializers.CharField(required=False, allow_blank=True)

    school_code = serializers.CharField(write_only=True, required=True)

    class Meta(BaseRoleCreateSerializer.Meta):
        fields = BaseRoleCreateSerializer.Meta.fields + (
            "qualification",
            "specialization",
            "department",
            "staff_id",
        )


class CustomAdminCreateSerializer(BaseRoleCreateSerializer):
    role = UserRole.ADMIN
    profile_model = AdminProfile

    profile_fields = ["admin_type", "position", "school_name"]

    admin_type = serializers.ChoiceField(choices=AdminType.choices, required=True)
    position = serializers.CharField(required=False, allow_blank=True)
    school_name = serializers.CharField(required=False, allow_blank=True)

    school_id = serializers.UUIDField(write_only=True, required=False)
    school_code = serializers.CharField(write_only=True, required=False)

    class Meta(BaseRoleCreateSerializer.Meta):
        fields = BaseRoleCreateSerializer.Meta.fields + (
            "admin_type",
            "school_id",
            "school_code",
            "position",
            "school_name",
        )


class OSNameSchema(BaseModelNoDefs):
    Android: Literal["Android"] | None = None
    iOS: Literal["iOS", "iPadOS"] | None = None  # noqa: N815
    web: Literal["iOS", "Windows", "Android"] | None = None


class ModelNameSchema(BaseModelNoDefs):
    Android: str | None = None
    iOS: str | None = None  # noqa: N815
    web: str | None = None


class OSVersionSchema(BaseModelNoDefs):
    Android: str | None = None
    iOS: str | None = None  # noqa: N815
    web: str | None = None


class UserDeviceInfoSchema(BaseModelNoDefs):
    osName: Literal["Android", "android", "iOS", "ios", "web", "Web"] | None = (
        None  # noqa: N815
    )
    modelName: str | None = None  # noqa: N815
    osVersion: str | None = None  # noqa: N815


class UserMetadataSchema(BaseModelNoDefs):
    push_notification_id: str | None
    device_info: UserDeviceInfoSchema | None


class UserSerializer:
    """Nested namespace for user-related serializers following Djoser pattern."""

    class AddOrRetrieveDevice(serializers.ModelSerializer):
        """Serializer for adding or retrieving device info via user email."""

        class Meta:
            model = User
            fields = ("email",)

    class Update(serializers.ModelSerializer):
        """Serializer for updating user information."""

        class Meta:
            model = User
            fields = (
                "name",
                "phone_number",
            )

    class Info(serializers.ModelSerializer):
        """Detailed user information (used in profile endpoints)."""

        role_display = serializers.CharField(source="get_role_display", read_only=True)

        class Meta:
            model = User
            fields = (
                "id",
                "email",
                "name",
                "phone_number",
                "role",
                "role_display",
                "is_verified",
                "date_joined",
                "last_login",
            )
            read_only_fields = [
                "id",
                "email",
                "role",
                "role_display",
                "date_joined",
                "last_login",
                "is_verified",
            ]


class GetUser(serializers.ModelSerializer):
    """Lightweight serializer for current authenticated user (e.g. /users/me/)."""

    role_display = serializers.CharField(source="get_role_display", read_only=True)

    class Meta:
        model = User
        fields = (
            "id",
            "email",
            "name",
            "phone_number",
            "role",
            "role_display",
            "is_active",
            "is_verified",
        )
        read_only_fields = [
            "id",
            "email",
            "role",
            "role_display",
            "is_active",
            "is_verified",
        ]


class EmailAndTokenSerializer(serializers.Serializer):
    email = serializers.EmailField()
    token = serializers.CharField()

    default_error_messages = {
        "invalid_token": "The token may have expired or is invalid.",
        "invalid_email": "No user found with that email. Create an account or try another email.",  # noqa: E501
    }

    def validate(self, attrs):
        validated_data = super().validate(attrs)

        # uid validation have to be here, because validate_<field_name>
        # doesn't work with modelserializer
        try:
            email = self.initial_data.get("email", "")
            self.user = User.objects.get(email=email)
        except (User.DoesNotExist, ValueError, TypeError, OverflowError) as e:
            key_error = "invalid_email"
            raise CustomError.BadRequest(
                {"email": self.error_messages[key_error]},
                code=key_error,
            ) from e

        is_token_valid = default_token_generator.check_token(
            self.user,
            self.initial_data.get("token", ""),
        )
        if is_token_valid:
            return validated_data
        key_error = "invalid_token"
        raise CustomError.BadRequest(
            {"token": self.error_messages[key_error]},
            code=key_error,
        )


class PasswordSerializer(serializers.Serializer):
    new_password = serializers.CharField(style={"input_type": "password"})

    def validate(self, attrs):
        user = getattr(self, "user", None) or self.context["request"].user
        # why assert? There are ValidationError / fail everywhere
        assert user is not None

        try:
            validate_password(attrs["new_password"], user)
        except django_exceptions.ValidationError as e:
            raise CustomError.BadRequest({"new_password": e.messages[0]})  # noqa: B904
        return super().validate(attrs)


class PasswordRetypeSerializer(PasswordSerializer):
    re_new_password = serializers.CharField(style={"input_type": "password"})

    default_error_messages = {
        "password_mismatch": settings.CONSTANTS.messages.PASSWORD_MISMATCH_ERROR,
    }

    def validate(self, attrs):
        attrs = super().validate(attrs)
        if attrs["new_password"] == attrs["re_new_password"]:
            return attrs
        return self.fail("password_mismatch")


class UsernameSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = (settings.LOGIN_FIELD,)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.username_field = settings.LOGIN_FIELD
        self._default_username_field = User.USERNAME_FIELD
        self.fields[f"new_{self.username_field}"] = self.fields.pop(self.username_field)

    def save(self, **kwargs):
        if self.username_field != self._default_username_field:
            kwargs[User.USERNAME_FIELD] = self.validated_data.get(
                f"new_{self.username_field}",
            )
        return super().save(**kwargs)


class UsernameRetypeSerializer(UsernameSerializer):
    default_error_messages = {
        "username_mismatch": settings.CONSTANTS.messages.USERNAME_MISMATCH_ERROR.format(
            settings.LOGIN_FIELD,
        ),
    }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["re_new_" + settings.LOGIN_FIELD] = serializers.CharField()

    def validate(self, attrs):
        attrs = super().validate(attrs)
        new_username = attrs[settings.LOGIN_FIELD]
        if new_username != attrs[f"re_new_{settings.LOGIN_FIELD}"]:
            return self.fail("username_mismatch")
        return attrs


class ActivationSerializer(EmailAndTokenSerializer):
    """
    Serializer for user activation.
    It validates the token and checks if the user is active.
    If the user is active, it raises a PermissionDenied exception.
    If the token is invalid, it raises a BadRequest exception.
    If the user is not active, it returns the validated data."""

    default_error_messages = {
        "stale_token": settings.CONSTANTS.messages.STALE_TOKEN_ERROR,
    }

    def validate(self, attrs):
        attrs = super().validate(attrs)
        if not self.user.is_active:
            return attrs
        raise PermissionDenied(self.error_messages["stale_token"])


class PasswordResetConfirmSerializer(EmailAndTokenSerializer, PasswordSerializer):
    pass


class PasswordResetConfirmRetypeSerializer(
    EmailAndTokenSerializer,
    PasswordRetypeSerializer,
):
    pass


class UsernameResetConfirmSerializer(EmailAndTokenSerializer, UsernameSerializer):
    pass


class UsernameResetConfirmRetypeSerializer(
    EmailAndTokenSerializer,
    UsernameRetypeSerializer,
):
    pass


class CustomTokenObtainPairSerializer(TokenObtainPairSerializer):
    email = serializers.EmailField()
    password = serializers.CharField()

    def get_setup_info(self, user: User):
        return {"user_info": user.accounts_dict, "is_verified": user.is_verified}

    def validate(self, attrs):
        authenticate_kwargs = {
            self.username_field: attrs[self.username_field],
            "password": attrs["password"],
        }
        with contextlib.suppress(KeyError):
            authenticate_kwargs["request"] = self.context["request"]

        self.user: User = authenticate(**authenticate_kwargs)
        if not self.user:
            if user := User.objects.filter(email=attrs["email"]).first():
                if not user.is_active:
                    context = {"user": user}
                    to = [get_user_email(user)]
                    settings.EMAIL.activation(self.context["request"], context).send(to)
                    msg = "Your account is not yet verified, kindly check yur email and proceed to verification"  # noqa: E501
                    raise PermissionDenied(
                        msg,
                    )
                if not api_settings.USER_AUTHENTICATION_RULE(self.user):
                    raise AuthenticationFailed(
                        detail="Login failed. Please check your email and password and try again.",  # noqa: E501
                    )

        data = super().validate(attrs)
        refresh = self.get_token(self.user)
        data["refresh"] = str(refresh)
        data["access"] = str(refresh.access_token)
        data["setup_info"] = None
        data["registration_complete"] = None
        data["setup_info"] = UserSerializer.Info(instance=self.user).data
        data["registration_complete"] = all([self.user.is_active])
        if api_settings.UPDATE_LAST_LOGIN:
            update_last_login(None, self.user)
        if not self.user.is_superuser:
            user_logged_in.send(
                sender=self.user.__class__,
                token=data["access"],
                user=self.user,
            )
        return data
