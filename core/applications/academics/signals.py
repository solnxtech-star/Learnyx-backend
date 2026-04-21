from django.db.models.signals import post_save
from django.dispatch import receiver

from core.applications.academics.models import TimeSlot


@receiver(post_save, sender="users.School")
def create_default_time_slots(sender, instance, created, **kwargs):
    """
    Automatically create default timetable slots when a new school is created.
    """

    if not created:
        return

    # Optional safety: prevent duplicates if signal ever re-runs
    if TimeSlot.objects.filter(school=instance).exists():
        return

    default_slots = [
        ("Period 1", "08:00", "08:40", 1),
        ("Period 2", "08:40", "09:20", 2),
        ("Period 3", "09:20", "10:00", 3),

        ("Break 1", "10:00", "10:20", 4),

        ("Period 4", "10:20", "11:00", 5),
        ("Period 5", "11:00", "11:40", 6),
        ("Period 6", "11:40", "12:20", 7),

        ("Lunch Break", "12:20", "13:00", 8),

        ("Period 7", "13:00", "13:40", 9),
        ("Period 8", "13:40", "14:20", 10),
        ("Period 9", "14:20", "15:00", 11),

        ("Break 2", "15:00", "15:20", 12),

        ("Period 10", "15:20", "16:00", 13),
        ("Period 11", "16:00", "16:40", 14),
        ("Period 12", "16:40", "17:00", 15),
    ]

    time_slots = [
        TimeSlot(
            school=instance,
            name=name,
            start_time=start,
            end_time=end,
            order=order,
            is_break="break" in name.lower(),
        )
        for name, start, end, order in default_slots
    ]

    TimeSlot.objects.bulk_create(time_slots)
