from __future__ import annotations

import threading
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from core.applications.users.models import School

_thread_locals = threading.local()

def set_current_school(school):
    """
    Set the current tenant in thread-local storage.
    Also stores db_alias so the router can read it
    without needing to re-fetch the school object.
    """
    _thread_locals.school = school
    _thread_locals.db_alias = school.effective_db_alias if school else "default"

def get_current_school():
    """Get the current tenant from thread-local storage."""
    return getattr(_thread_locals, "school", None)

def get_current_db_alias() -> str:
    """
    Return the database alias for the current tenant.
    'default' when no tenant is set or school is on shared tier.
    'school_<slug>' when school is on isolated tier.
    """
    return getattr(_thread_locals, "db_alias", "default")

def clear_current_school():
    """Clear the current tenant from thread-local storage."""
    _thread_locals.school = None
