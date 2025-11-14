# from drf_spectacular.utils import extend_schema, extend_schema_view
# from core.applications.users.api import serializers as user_serializers


# user_schema = extend_schema_view(

#     list=extend_schema(
#         summary="List all users",
#         description=(
#             "Retrieve a paginated list of all registered users in the system.\n\n"
#             "Accessible only by admin users. Supports filters, pagination, and search."
#         ),
#         responses={200: user_serializers.CustomUserSerializer(many=True)},
#     ),

#     retrieve=extend_schema(
#         summary="Retrieve a user by ID",
#         description="Get full details of a specific user by their unique identifier (admin-only).",
#         responses={200: user_serializers.CustomUserSerializer},
#     ),

#     me=extend_schema(
#         summary="Authenticated user profile",
#         description=(
#             "Retrieve or update the profile of the currently authenticated user.\n\n"
#             "Supports GET (retrieve), PUT/PATCH (update), and DELETE (deactivate) operations."
#         ),
#         responses={200: user_serializers.CustomUserSerializer},
#     ),

#     get_by_email=extend_schema(
#         summary="Fetch user by email",
#         description=(
#             "Retrieve basic information of a user by email address.\n\n"
#             "Useful for quick lookups or pre-verification checks."
#         ),
#         parameters=[],
#         responses={200: user_serializers.GetUserSerializer},
#     ),


#     register_student=extend_schema(
#         summary="Student Self-Registration",
#         description=(
#             "Allow a student to register a new account.\n\n"
#             "The account remains pending approval until verified by an admin."
#         ),
#         request=user_serializers.UserRegistrationSerializer,
#         responses={201: user_serializers.CustomUserSerializer},
#     ),

#     invite_teacher=extend_schema(
#         summary="Admin: Invite a Teacher",
#         description=(
#             "Send an invitation to a teacher via email. "
#             "An inactive account will be created with an invitation token.\n\n"
#             "Only admin users can perform this action."
#         ),
#         request=user_serializers.TeacherInviteSerializer,
#         responses={201: user_serializers.CustomUserSerializer},
#     ),

#     activate_teacher=extend_schema(
#         summary="Teacher Account Activation",
#         description=(
#             "Activate an invited teacher’s account using the invitation token. "
#             "The teacher will set their password and activate the account."
#         ),
#         request=user_serializers.TeacherActivationSerializer,
#         responses={200: user_serializers.CustomUserSerializer},
#     ),

#     # ============================================================
#     #  Admin: Account Creation
#     # ============================================================
#     create_parent=extend_schema(
#         summary="Admin: Create Parent Account",
#         description=(
#             "Create a parent account manually from the admin dashboard.\n\n"
#             "This endpoint automatically creates the corresponding `ParentProfile` "
#             "and sets related fields such as occupation, address, and phone number."
#         ),
#         request=user_serializers.AdminCreateParentSerializer,
#         responses={201: user_serializers.CustomUserSerializer},
#     ),

#     create_admin=extend_schema(
#         summary="Admin: Create Admin Account",
#         description=(
#             "Allows an existing admin to create another admin account.\n\n"
#             "Useful for multi-admin schools or organizations."
#         ),
#         request=user_serializers.AdminCreateAdminSerializer,
#         responses={201: user_serializers.CustomUserSerializer},
#     ),

#     # ============================================================
#     #  Authentication & Password
#     # ============================================================
#     login=extend_schema(
#         summary="User Login (JWT)",
#         description=(
#             "Authenticate a user via email and password.\n\n"
#             "Returns JWT access and refresh tokens along with basic user information."
#         ),
#         request=user_serializers.CustomTokenObtainPairSerializer,
#         responses={200: user_serializers.CustomUserSerializer},
#     ),

#     logout=extend_schema(
#         summary="Logout User",
#         description=(
#             "Logout the currently authenticated user.\n\n"
#             "Invalidates the current JWT or session depending on configuration."
#         ),
#     ),

#     activate=extend_schema(
#         summary="Account Activation (Generic)",
#         description=(
#             "Activate a user account via email confirmation link.\n\n"
#             "Follows Djoser-style token activation flow."
#         ),
#     ),

#     resend_activation=extend_schema(
#         summary="Resend Activation Email",
#         description="Resend the account activation email to users who haven't activated yet.",
#     ),

#     reset_password=extend_schema(
#         summary="Request Password Reset",
#         description=(
#             "Send a password reset email containing a token link.\n\n"
#             "The user can then confirm it using the `/reset_password_confirm/` endpoint."
#         ),
#     ),

#     reset_password_confirm=extend_schema(
#         summary="Confirm Password Reset",
#         description=(
#             "Confirm the password reset using the token sent by email.\n\n"
#             "Allows setting a new password for the account."
#         ),
#     ),

#     set_password=extend_schema(
#         summary="Change Password (Authenticated User)",
#         description="Allow authenticated users to securely update their password.",
#     ),

#     # ============================================================
#     #  Device & Metadata (Optional)
#     # ============================================================
#     add_or_update_device=extend_schema(
#         summary="Register or Update Device Info",
#         description=(
#             "Attach device metadata such as OS, model, or push notification ID to the user.\n\n"
#             "Useful for analytics or push notifications."
#         ),
#         request=user_serializers.UserSerializer.AddOrRetrieveDevice,
#         responses={200: user_serializers.CustomUserSerializer},
#     ),

#     list_devices=extend_schema(
#         summary="List User Devices",
#         description="List all devices associated with the authenticated user's account.",
#     ),
# )
