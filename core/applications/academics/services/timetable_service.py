from django.db import transaction

from core.applications.academics.models import Timetable
from core.applications.academics.models import TimetableEntry


class TimetableService:

    @staticmethod
    def activate(timetable):
        """Activate the given timetable and deactivate any other active timetables for the same class."""
        with transaction.atomic():
            Timetable.objects.filter(
                class_room=timetable.class_room,
                is_active=True
            ).exclude(pk=timetable.pk).update(is_active=False)
            timetable.is_active = True
            timetable.save()

    @staticmethod
    def deactivate(timetable):
        """Deactivate the given timetable."""
        with transaction.atomic():
            timetable.is_active = False
            timetable.save()

    @staticmethod
    @transaction.atomic
    def clone(timetable, name):
        """
        Clone the given timetable with a new name. The cloned timetable will be inactive by default.
        Args:
            timetable (Timetable): The timetable to clone.
            name (str): The name for the cloned timetable.
            Returns:
            Timetable: The newly cloned timetable instance.
        """

        cloned = Timetable.objects.create(
            school=timetable.school,
            class_room=timetable.class_room,
            timetable_type=timetable.timetable_type,
            name=name,
            academic_session=timetable.academic_session,
            term=timetable.term,
            start_date=timetable.start_date,
            end_date=timetable.end_date,
            is_active=False
        )

        entries = [
            TimetableEntry(
                timetable=cloned,
                school=e.school,
                class_room=e.class_room,
                day_of_week=e.day_of_week,
                date=e.date,
                time_slot=e.time_slot,
                subject=e.subject,
                teacher=e.teacher
            )
            for e in timetable.entries.all()
        ]

        TimetableEntry.objects.bulk_create(entries)

        return cloned
