from __future__ import annotations

import logging

from django.conf import settings

from core.helper.tenants import get_current_db_alias

logger = logging.getLogger(__name__)


# ------------------------------------------------------------------
# Models that ALWAYS live in the master/default database.
# These are platform-level models — not tenant data.
# ------------------------------------------------------------------
MASTER_MODELS: frozenset[str] = frozenset({
    "school",
    "user",
    "subscriptionplan",
    "schoolsubscription",
    "subscriptioninvoice",
})

# ------------------------------------------------------------------
# Django internal + third-party apps that always use default.
# ------------------------------------------------------------------
MASTER_APPS: frozenset[str] = frozenset({
    "auth",
    "contenttypes",
    "sessions",
    "admin",
    "account",       # allauth
    "socialaccount", # allauth
})


class TenantDatabaseRouter:
    """
    Routes every Django ORM query to the correct database
    based on the current tenant's db_alias set by CurrentSchoolMiddleware.

    Routing rules:
    ┌─────────────────────────────────────────────────────────┐
    │  Master models (School, User, Subscription)             │
    │  Django internal apps (auth, sessions, admin)           │
    │  → ALWAYS route to 'default'                            │
    ├─────────────────────────────────────────────────────────┤
    │  All other models (StudentProfile, ClassRoom, etc.)     │
    │  → Route to current tenant's db_alias                   │
    │    'default'          for SHARED tier schools           │
    │    'school_greenfield' for ISOLATED tier schools        │
    └─────────────────────────────────────────────────────────┘

    Safety rules:
    - Unknown/unregistered db_alias falls back to 'default'
    - Logs a warning when fallback is triggered
    - Never raises — a wrong DB is better than a crash
    """

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _get_tenant_db(self) -> str:
        """
        Read the current tenant's database alias from thread-local.
        Returns 'default' when:
          - No tenant is set (unauthenticated / management commands)
          - School is on the shared tier
          - School is on isolated tier but DB isn't registered yet
        """
        alias = get_current_db_alias()

        # Safety — verify alias is actually registered in settings
        if alias != "default" and alias not in settings.DATABASES:
            logger.warning(
                "TenantDatabaseRouter: alias '%s' not found in DATABASES — "
                "falling back to 'default'. "
                "School may not have been provisioned yet.",
                alias,
            )
            return "default"

        return alias

    def _is_master(self, model) -> bool:
        """
        True if this model always belongs on the master/default database.
        Checks both app_label and model_name.
        """
        return (
            model._meta.app_label in MASTER_APPS
            or model._meta.model_name in MASTER_MODELS
        )

    # ------------------------------------------------------------------
    # Django Router Interface
    # ------------------------------------------------------------------

    def db_for_read(self, model, **hints) -> str:
        """Called before every SELECT query."""
        if self._is_master(model):
            return "default"

        db = self._get_tenant_db()
        logger.debug(
            "READ  %-40s → %s",
            model._meta.label,
            db,
        )
        return db

    def db_for_write(self, model, **hints) -> str:
        """Called before every INSERT / UPDATE / DELETE query."""
        if self._is_master(model):
            return "default"

        db = self._get_tenant_db()
        logger.debug(
            "WRITE %-40s → %s",
            model._meta.label,
            db,
        )
        return db

    def allow_relation(self, obj1, obj2, **hints) -> bool | None:
        """
        Called when Django checks if a FK/M2M relation between
        two objects is valid.

        Rules:
        - Objects on the same database → always allowed
        - One object on 'default' (master model) → allowed
          because master models are accessible from all databases
        - Objects on two different tenant databases → denied
          (cross-tenant relation — should never happen)
        """
        db1 = obj1._state.db
        db2 = obj2._state.db

        if db1 == db2:
            return True

        # Allow relations between master DB and any tenant DB
        # e.g. StudentProfile (tenant) → User (master)
        if "default" in (db1, db2):
            return True

        # Two different non-default databases → cross-tenant contamination
        logger.error(
            "allow_relation DENIED: %s (db=%s) ↔ %s (db=%s) — "
            "cross-tenant relation detected.",
            obj1.__class__.__name__, db1,
            obj2.__class__.__name__, db2,
        )
        return False

    def allow_migrate(self, db, app_label, model_name=None, **hints) -> bool:
        """
        Controls which databases each migration runs on.

        Rules:
        - Master apps (auth, admin, etc.) → only on 'default'
        - Master models (School, User etc) → only on 'default'
        - All other tenant models          → on ALL databases
          (both default and every isolated tenant DB)

        This means when you run:
            manage.py migrate                          → runs on default
            manage.py migrate --database=school_greenfield → runs tenant migrations only
        """
        if app_label in MASTER_APPS:
            return db == "default"

        if model_name and model_name.lower() in MASTER_MODELS:
            return db == "default"

        # Tenant models migrate on every registered database
        return True
