import threading

_thread_locals = threading.local()

def set_current_school(school):
    """Set the current tenant in thread-local storage."""
    _thread_locals.school = school

def get_current_school():
    """Get the current tenant from thread-local storage."""
    return getattr(_thread_locals, "school", None)
