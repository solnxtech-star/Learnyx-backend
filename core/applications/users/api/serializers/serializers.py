import contextlib
import uuid
from typing import Literal

from django.contrib.auth import authenticate
from django.contrib.auth import user_logged_in
from django.contrib.auth.models import update_last_login
from django.contrib.auth.password_validation import validate_password
from django.core import exceptions as django_exceptions
from django.db import transaction
from djoser.compat import get_user_email
from djoser.conf import settings
from djoser.serializers import UserCreateSerializer
from rest_framework import serializers
from rest_framework.exceptions import AuthenticationFailed
from rest_framework.exceptions import PermissionDenied
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from rest_framework_simplejwt.settings import api_settings

from core.applications.academics.models import AcademicSession, ClassRoom
from core.applications.academics.models import StudentClassAssignment
from core.applications.users.models import AdminProfile
from core.applications.users.models import School
from core.applications.users.models import StudentProfile
from core.applications.users.models import TeacherProfile
from core.applications.users.models import User
from core.applications.users.token import default_token_generator
from core.helper.custom_exceptions import CustomError
from core.helper.enums import AdminType
from core.helper.enums import AdmissionStatus
from core.helper.enums import Gender
from core.helper.enums import UserRole
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


# ------------------------
# BaseRoleCreateSerializer
# ------------------------
class BaseRoleCreateSerializer(UserCreateSerializer):
    """
    Base serializer for role-based user registration.

    Responsibilities
    ----------------
    - Password confirmation
    - Safe preprocessing of serializer-only fields
    - Multi-tenant school resolution
    - Role assignment
    - Dynamic profile creation
    """

    re_password = serializers.CharField(write_only=True, required=True)

    role = None
    profile_model = None
    profile_fields = []

    school_code = serializers.CharField(write_only=True, required=False)
    school_id = serializers.UUIDField(write_only=True, required=False)

    class Meta(UserCreateSerializer.Meta):
        model = User
        fields = (
            *UserCreateSerializer.Meta.fields,
            "re_password",
            "school_code",
            "school_id",
        )
        extra_kwargs = {
            "password": {"write_only": True},
            "re_password": {"write_only": True},
        }

    def validate(self, attrs):
        """
        Validate registration data while keeping compatibility
        with Djoser's internal validation.
        """

        # --------------------------------------------------
        # Normalize name fields BEFORE Djoser validation
        # --------------------------------------------------
        first_name = attrs.pop("first_name", None)
        last_name = attrs.pop("last_name", None)

        if first_name or last_name:
            attrs["name"] = f"{first_name or ''} {last_name or ''}".strip()

        # --------------------------------------------------
        # Password confirmation
        # --------------------------------------------------
        re_password = attrs.pop("re_password", None)
        if not re_password:
            raise CustomError.BadRequest({"re_password": "This field is required."})

        self._re_password = re_password

        # --------------------------------------------------
        # Extract profile fields
        # --------------------------------------------------
        self._profile_data = {
            k: v for k, v in attrs.items() if k in self.profile_fields
        }

        for k in self.profile_fields:
            attrs.pop(k, None)

        # --------------------------------------------------
        # Extract school identifiers
        # --------------------------------------------------
        self._school_code = attrs.pop("school_code", None)
        self._school_id = attrs.pop("school_id", None)

        # --------------------------------------------------
        # Resolve school via tenant middleware
        # --------------------------------------------------
        request = self.context.get("request")
        self.school = getattr(request, "current_school", None)

        self._validate_school_assignment()

        # --------------------------------------------------
        # Run Djoser validation AFTER cleaning attrs
        # --------------------------------------------------
        attrs = super().validate(attrs)

        if attrs["password"] != self._re_password:
            raise CustomError.BadRequest({"re_password": "Passwords do not match."})

        return attrs

    def _validate_school_assignment(self):
        """
        Resolve the school for the current tenant.
        """

        if self.school:
            self._school_code = self.school.school_code
            self._school_id = self.school.id
            return

        if self.role in [UserRole.STUDENT, UserRole.TEACHER]:

            if not self._school_code:
                raise CustomError.BadRequest({"school_code": "This field is required."})

            self.school = School.objects.filter(
                school_code=self._school_code,
                is_active=True,
            ).first()

            if not self.school:
                raise CustomError.NotFound({"school_code": "Invalid school code."})

        elif self.role == UserRole.ADMIN:

            if self._school_id:
                self.school = School.objects.filter(
                    id=self._school_id,
                    is_active=True,
                ).first()

                if not self.school:
                    raise CustomError.NotFound({"school_id": "Invalid school ID."})

            elif self._school_code:

                self.school = School.objects.filter(
                    school_code=self._school_code,
                    is_active=True,
                ).first()

                if not self.school:
                    raise CustomError.NotFound({"school_code": "Invalid school code."})

            else:
                raise CustomError.BadRequest(
                    {"school": "Provide school_id or school_code."}
                )

        # --------------------------------------------------
        # Role-specific profile preparation
        # --------------------------------------------------
        if self.role == UserRole.TEACHER:

            if not self._profile_data.get("staff_id"):
                self._profile_data["staff_id"] = (
                    f"STF-{uuid.uuid4().hex[:8].upper()}"
                )

    @transaction.atomic
    def create(self, validated_data):
        """
        Create the user and its related role profile.
        """

        user = super().create(validated_data)

        user.role = self.role

        if user.school is None:
            user.school = self.school

        user.save(update_fields=["role", "school"])

        # --------------------------------------------------
        # Profile creation
        # --------------------------------------------------
        if self.profile_model:

            profile_data = dict(self._profile_data)

            classroom_id = profile_data.pop("classroom_id", None)

            if classroom_id:

                classroom = ClassRoom.objects.for_school(self.school).filter(
                    id=classroom_id
                ).first()

                if not classroom:
                    raise CustomError.NotFound(
                        {"classroom_id": "Invalid classroom for this school"}
                    )

                profile_data["classroom"] = classroom

            self.profile_model.objects.create(
                user=user,
                **profile_data,
            )

        return user

# ------------------------
# CustomUserCreateSerializer (Student)
# ------------------------
class CustomUserCreateSerializer(BaseRoleCreateSerializer):
    """
    Serializer for Student registration.

    This serializer extends `BaseRoleCreateSerializer` and creates a student
    user with minimal required information.

    Required Fields
    ----------------
    - first_name
    - last_name
    - email
    - password
    - re_password
    - school_code (optional if tenant middleware resolves school)

    Behaviour
    ----------
    - Combines `first_name` and `last_name` into the `User.name` field.
    - Assigns the user role as STUDENT.
    - Automatically creates a `StudentProfile`.
    - School is resolved via tenant middleware or provided `school_code`.
    """

    role = UserRole.STUDENT
    profile_model = StudentProfile
    profile_fields = []  # No profile fields required at registration

    # ----------------------------------------
    # Serializer-only fields (not in User model)
    # ----------------------------------------
    first_name = serializers.CharField(write_only=True, required=True)
    last_name = serializers.CharField(write_only=True, required=True)

    # Used when school is not resolved via middleware
    school_code = serializers.CharField(write_only=True, required=False)

    class Meta(BaseRoleCreateSerializer.Meta):
        """
        Extend base serializer fields but keep the registration minimal.
        """
        fields = (
            "email",
            "password",
            "re_password",
            "first_name",
            "last_name",
            "school_code",
        )

    def validate(self, attrs):
        """
        Perform additional validation and transform name fields.

        Steps
        -----
        1. Run base validations (password confirmation, school resolution).
        2. Convert `first_name` + `last_name` → `User.name`.
        3. Remove serializer-only fields before model creation.
        """

        # Run BaseRoleCreateSerializer validation
        attrs = super().validate(attrs)

        # Extract serializer-only fields
        first_name = attrs.pop("first_name", "").strip()
        last_name = attrs.pop("last_name", "").strip()

        # Combine into full name for the User model
        attrs["name"] = f"{first_name} {last_name}".strip()

        return attrs

    @transaction.atomic
    def create(self, validated_data):
        """
        Create the student user and associated profile.

        The base serializer handles:
        - User creation
        - Role assignment
        - School assignment
        - StudentProfile creation

        This method simply delegates to the base implementation.
        """

        user = super().create(validated_data)
        return user
# ------------------------
class StudentOnboardingSerializer(serializers.Serializer):
    """
    Handles the onboarding of a student after account creation.

    Allows a student to provide additional profile details and optionally select a classroom
    for the current academic session.

    Responsibilities
    ----------------
    • Update StudentProfile fields.
    • Validate classroom belongs to the user's school.
    • Assign the student to a classroom for the active academic session.
    • Ensure only one active classroom assignment exists.

    Security
    --------
    • The user must exist in the system.
    • Classroom lookups are restricted to the user's school.
    """

    user_id = serializers.IntegerField(required=True)  # User must be provided
    gender = serializers.ChoiceField(choices=Gender.choices, required=False)
    classroom_id = serializers.CharField(required=False, allow_blank=True)

    guardian_name = serializers.CharField(required=False, allow_blank=True)
    guardian_phone = serializers.CharField(required=False, allow_blank=True)
    address = serializers.CharField(required=False, allow_blank=True)
    admission_date = serializers.DateField(required=False)

    def validate(self, attrs):
        """
        Validate request data and resolve related objects.

        Ensures:
        • User exists.
        • Student profile exists.
        • Classroom (if provided) belongs to the user's school.
        """
        user_id = attrs.get("user_id")
        user = User.objects.filter(id=user_id).first()

        if not user:
            raise CustomError.NotFound({"user_id": "User not found."})

        # Optional: ensure user role is STUDENT
        if user.role != UserRole.STUDENT:
            raise CustomError.BadRequest(
                {"detail": "Only students are allowed to complete onboarding."}
            )

        profile = getattr(user, "studentprofile", None)
        if not profile:
            raise CustomError.NotFound({"profile": "Student profile could not be found."})

        self.profile = profile
        self.classroom = None

        # Validate classroom if provided
        classroom_id = attrs.get("classroom_id")
        if classroom_id:
            classroom = (
                ClassRoom.objects.for_school(user.school)
                .filter(id=classroom_id)
                .first()
            )
            if not classroom:
                raise CustomError.NotFound(
                    {"classroom_id": "Invalid classroom for this school."}
                )
            self.classroom = classroom

        return attrs

    @transaction.atomic
    def save(self, **kwargs):
        """
        Persist onboarding data:

        1. Update the student profile fields.
        2. Assign the student to a classroom (if provided).
        3. Ensure only one active StudentClassAssignment exists.
        """
        profile = self.profile
        data = self.validated_data

        # -----------------------------
        # Update profile fields
        # -----------------------------
        profile.gender = data.get("gender", profile.gender)
        profile.guardian_name = data.get("guardian_name", profile.guardian_name)
        profile.guardian_phone = data.get("guardian_phone", profile.guardian_phone)
        profile.address = data.get("address", profile.address)
        profile.admission_date = data.get("admission_date", profile.admission_date)

        profile.save(
            update_fields=[
                "gender",
                "guardian_name",
                "guardian_phone",
                "address",
                "admission_date",
            ]
        )

        # -----------------------------
        # Classroom assignment
        # -----------------------------
        if self.classroom:
            profile.sync_current_class_fields(self.classroom)

            # Retrieve the active academic session
            session = (
                AcademicSession.objects.for_school(profile.school)
                .filter(is_active=True)
                .first()
            )
            if not session:
                raise CustomError.NotFound(
                    {"academic_session": "No active academic session found."}
                )

            # Deactivate existing active assignments
            StudentClassAssignment.objects.filter(
                student=profile,
                is_active=True,
            ).update(is_active=False)

            # Create new assignment
            StudentClassAssignment.objects.create(
                student=profile,
                classroom=self.classroom,
                academic_session=session,
                is_active=True,
            )

        return profile

class StudentPhotoUploadSerializer(serializers.Serializer):
    """
    Handles uploading a photo for a student's profile.

    Security
    --------
    • Ensures the user exists in the system.
    • Ensures the user has a student profile.
    """

    user_id = serializers.IntegerField(required=True)  # Integer PK
    photo = serializers.ImageField(required=True)

    def validate(self, attrs):
        """
        Ensure the user exists and has a student profile.
        """
        user_id = attrs.get("user_id")
        user = User.objects.filter(id=user_id).first()

        if not user:
            raise CustomError.NotFound({"user_id": "User not found."})

        profile = getattr(user, "studentprofile", None)
        if not profile:
            raise CustomError.NotFound({"profile": "Student profile not found."})

        self.profile = profile
        return attrs

    def save(self, **kwargs):
        """
        Save the uploaded photo to the student's profile.
        """
        profile = self.profile
        profile.photo = self.validated_data["photo"]
        profile.save(update_fields=["photo"])
        return profile

# ------------------------
# CustomTeacherCreateSerializer
# ------------------------
class CustomTeacherCreateSerializer(BaseRoleCreateSerializer):
    role = UserRole.TEACHER
    profile_model = TeacherProfile
    profile_fields = ["qualification", "specialization", "department", "staff_id"]

    qualification = serializers.CharField(required=False, allow_blank=True)
    specialization = serializers.CharField(required=False, allow_blank=True)
    department = serializers.CharField(required=False, allow_blank=True)
    staff_id = serializers.CharField(required=False, allow_blank=True)
    school_code = serializers.CharField(write_only=True, required=False)

    class Meta(BaseRoleCreateSerializer.Meta):
        fields = BaseRoleCreateSerializer.Meta.fields + (
            "qualification",
            "specialization",
            "department",
            "staff_id",
        )


# ------------------------
# CustomAdminCreateSerializer
# ------------------------
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
    osName: Literal["Android", "android", "iOS", "ios", "web", "Web"] | None = None
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
