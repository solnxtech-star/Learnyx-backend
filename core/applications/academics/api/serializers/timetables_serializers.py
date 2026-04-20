from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils.translation import gettext_lazy as _
from rest_framework import serializers

from core.applications.academics.models import AcademicSession
from core.applications.academics.models import AcademicTerm
from core.applications.academics.models import ClassRoom
from core.applications.academics.models import Subject
from core.applications.academics.models import TimeSlot
from core.applications.academics.models import Timetable
from core.applications.academics.models import TimetableEntry
from core.applications.users.models import School


class TimeSlotSerializer(serializers.ModelSerializer):
    class Meta:
        model = TimeSlot
        fields = ["id", "name", "start_time", "end_time", "is_break"]

class SubjectSerializer(serializers.ModelSerializer):
    class Meta:
        model = Subject
        fields = ["id", "name", "code", "class_level"]


class TimetableEntrySerializer(serializers.ModelSerializer):
    # Readable fields for response
    day_of_week_display = serializers.CharField(source="get_day_of_week_display", read_only=True)
    time_slot_detail = TimeSlotSerializer(source="time_slot", read_only=True)
    subject_detail = SubjectSerializer(source="subject", read_only=True)
    teacher_name = serializers.SerializerMethodField()

    class Meta:
        model = TimetableEntry
        fields = [
            "id", "timetable", "school", "class_room",
            "day_of_week", "day_of_week_display",
            "date", "time_slot", "time_slot_detail",
            "subject", "subject_detail",
            "teacher", "teacher_name"
        ]
        read_only_fields = ["id"]

    def get_teacher_name(self, obj):
        """Returns the full name of the teacher if available, otherwise returns None."""
        if obj.teacher:
            return f"{obj.teacher.first_name} {obj.teacher.last_name}"
        return None

    def validate(self, data):
        """
        Custom validation to ensure:
        - For CLASS timetable, day_of_week is required and date should not be set.
        - For EXAM timetable, date is required and day_of_week should not be set.
        - Prevent duplicate time slots for the same day (for CLASS) or same date (for EXAM) within the same timetable.
        """

        timetable = data.get("timetable")
        day_of_week = data.get("day_of_week")
        date = data.get("date")

        if timetable:
            if timetable.timetable_type == "CLASS":
                # For class timetable, day_of_week is required
                if not day_of_week:
                    raise serializers.ValidationError({
                        "day_of_week": _("Day of week is required for class timetable.")
                    })
                if date:
                    raise serializers.ValidationError({
                        "date": _("Date should not be set for class timetable. Use day_of_week instead.")
                    })

                # Check for duplicate slot in the same timetable
                if TimetableEntry.objects.filter(
                    timetable=timetable,
                    day_of_week=day_of_week,
                    time_slot=data.get("time_slot")
                ).exists():
                    raise serializers.ValidationError({
                        "non_field_errors": _("Time slot already exists for this day in the timetable.")
                    })

            else:  # EXAM timetable
                # For exam timetable, date is required
                if not date:
                    raise serializers.ValidationError({
                        "date": _("Date is required for exam timetable.")
                    })
                if day_of_week:
                    raise serializers.ValidationError({
                        "day_of_week": _("Day of week should not be set for exam timetable. Use date instead.")
                    })

                # Check for duplicate slot on same date
                if TimetableEntry.objects.filter(
                    timetable=timetable,
                    date=date,
                    time_slot=data.get("time_slot")
                ).exists():
                    raise serializers.ValidationError({
                        "non_field_errors": _("Time slot already exists for this date in the timetable.")
                    })

        # Auto-populate school and class_room from timetable
        if timetable:
            data["school"] = timetable.school
            data["class_room"] = timetable.class_room

        return data

class TimetableListSerializer(serializers.ModelSerializer):
    """Simplified serializer for list view"""
    timetable_type_display = serializers.CharField(source="get_timetable_type_display", read_only=True)
    school_name = serializers.CharField(source="school.name", read_only=True)
    class_room_name = serializers.CharField(source="class_room.name", read_only=True)
    academic_session_name = serializers.CharField(source="academic_session.name", read_only=True)
    term_name = serializers.CharField(source="term.name", read_only=True)
    entry_count = serializers.IntegerField(read_only=True)

    class Meta:
        model = Timetable
        fields = [
            "id", "name", "school", "school_name",
            "class_room", "class_room_name",
            "timetable_type", "timetable_type_display",
            "academic_session", "academic_session_name",
            "term", "term_name",
            "start_date", "end_date",
            "is_active", "entry_count", "created_at", "modified_at"
        ]
        read_only_fields = ["id", "created_at", "modified_at"]

class TimetableDetailSerializer(serializers.ModelSerializer):
    """Detailed serializer with nested entries"""
    timetable_type_display = serializers.CharField(source="get_timetable_type_display", read_only=True)
    school_name = serializers.CharField(source="school.name", read_only=True)
    class_room_name = serializers.CharField(source="class_room.name", read_only=True)
    academic_session_name = serializers.CharField(source="academic_session.name", read_only=True)
    term_name = serializers.CharField(source="term.name", read_only=True)
    entries = TimetableEntrySerializer(many=True, read_only=True)

    class Meta:
        model = Timetable
        fields = [
            "id", "name", "school", "school_name",
            "class_room", "class_room_name",
            "timetable_type", "timetable_type_display",
            "academic_session", "academic_session_name",
            "term", "term_name",
            "start_date", "end_date",
            "is_active", "entries",
            "created_at", "modified_at"
        ]
        read_only_fields = ["id", "created_at", "modified_at"]

class TimetableEntryCreateUpdateSerializer(serializers.ModelSerializer):
    """Serializer for creating/updating entries within timetable"""

    class Meta:
        model = TimetableEntry
        fields = [
            "id", "day_of_week", "date", "time_slot",
            "subject", "teacher"
        ]

    def validate(self, data):
        # Get timetable from context
        timetable = self.context.get("timetable")
        if not timetable and self.instance:
            timetable = self.instance.timetable

        if not timetable:
            raise serializers.ValidationError(_("Timetable is required"))

        day_of_week = data.get("day_of_week")
        date = data.get("date")
        time_slot = data.get("time_slot")

        if timetable.timetable_type == "CLASS":
            if not day_of_week:
                raise serializers.ValidationError({
                    "day_of_week": _("Day of week is required for class timetable.")
                })
            if date:
                raise serializers.ValidationError({
                    "date": _("Date should not be set for class timetable.")
                })

            # Check for duplicates (exclude current instance if updating)
            queryset = TimetableEntry.objects.filter(
                timetable=timetable,
                day_of_week=day_of_week,
                time_slot=time_slot
            )
            if self.instance:
                queryset = queryset.exclude(id=self.instance.id)

            if queryset.exists():
                raise serializers.ValidationError({
                    "non_field_errors": _("Time slot already exists for this day.")
                })

        else:  # EXAM
            if not date:
                raise serializers.ValidationError({
                    "date": _("Date is required for exam timetable.")
                })
            if day_of_week:
                raise serializers.ValidationError({
                    "day_of_week": _("Day of week should not be set for exam timetable.")
                })

            # Check for duplicates
            queryset = TimetableEntry.objects.filter(
                timetable=timetable,
                date=date,
                time_slot=time_slot
            )
            if self.instance:
                queryset = queryset.exclude(id=self.instance.id)

            if queryset.exists():
                raise serializers.ValidationError({
                    "non_field_errors": _("Time slot already exists for this date.")
                })

        return data

class TimetableCreateUpdateSerializer(serializers.ModelSerializer):
    """Serializer for creating/updating timetable with nested entries"""
    entries = TimetableEntryCreateUpdateSerializer(many=True, required=False)

    class Meta:
        model = Timetable
        fields = [
            "id", "name", "school", "class_room",
            "timetable_type", "academic_session", "term",
            "start_date", "end_date", "is_active", "entries"
        ]
        read_only_fields = ["id"]

    def validate(self, data):
        # Validate term belongs to session
        term = data.get("term")
        academic_session = data.get("academic_session")

        if term and academic_session:
            if term.session_id != academic_session.id:
                raise serializers.ValidationError({
                    "term": _("Selected term does not belong to the academic session.")
                })

        # Validate class belongs to school
        class_room = data.get("class_room")
        school = data.get("school")

        if class_room and school:
            if class_room.school_id != school.id:
                raise serializers.ValidationError({
                    "class_room": _("Classroom must belong to the same school.")
                })

        # Validate dates
        start_date = data.get("start_date")
        end_date = data.get("end_date")

        if start_date and end_date:
            if end_date <= start_date:
                raise serializers.ValidationError({
                    "end_date": _("End date must be after start date.")
                })

        return data

    @transaction.atomic
    def create(self, validated_data):
        entries_data = validated_data.pop("entries", [])
        timetable = Timetable.objects.create(**validated_data)

        # Create entries
        for entry_data in entries_data:
            entry_data["timetable"] = timetable
            entry_data["school"] = timetable.school
            entry_data["class_room"] = timetable.class_room
            TimetableEntry.objects.create(**entry_data)

        return timetable

    @transaction.atomic
    def update(self, instance, validated_data):
        entries_data = validated_data.pop("entries", None)

        # Update timetable fields
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()

        # Handle entries if provided
        if entries_data is not None:
            # Get existing entry IDs
            existing_entry_ids = set(instance.entries.values_list("id", flat=True))
            updated_entry_ids = set()

            for entry_data in entries_data:
                entry_id = entry_data.get("id")
                entry_data["timetable"] = instance
                entry_data["school"] = instance.school
                entry_data["class_room"] = instance.class_room

                if entry_id:
                    # Update existing entry
                    entry_instance = TimetableEntry.objects.get(id=entry_id, timetable=instance)
                    for attr, value in entry_data.items():
                        setattr(entry_instance, attr, value)
                    entry_instance.save()
                    updated_entry_ids.add(entry_id)
                else:
                    # Create new entry
                    new_entry = TimetableEntry.objects.create(**entry_data)
                    updated_entry_ids.add(new_entry.id)

            # Delete entries that were not included in the update
            entries_to_delete = existing_entry_ids - updated_entry_ids
            TimetableEntry.objects.filter(id__in=entries_to_delete).delete()

        return instance

class TimetableBulkCreateSerializer(serializers.Serializer):
    """Serializer for bulk creating timetables for multiple classes"""
    school_id = serializers.IntegerField()
    academic_session_id = serializers.IntegerField()
    term_id = serializers.IntegerField()
    timetable_type = serializers.ChoiceField(choices=Timetable.TimetableType.choices)
    start_date = serializers.DateField()
    end_date = serializers.DateField()
    class_ids = serializers.ListField(child=serializers.IntegerField())
    name_prefix = serializers.CharField(max_length=100, required=False, default="Timetable")

    def validate(self, data):
        # Validate school exists
        if not School.objects.filter(id=data["school_id"]).exists():
            raise serializers.ValidationError({"school_id": _("School not found.")})

        # Validate session exists
        if not AcademicSession.objects.filter(id=data["academic_session_id"]).exists():
            raise serializers.ValidationError({"academic_session_id": _("Academic session not found.")})

        # Validate term exists and belongs to session
        term = AcademicTerm.objects.filter(
            id=data["term_id"],
            session_id=data["academic_session_id"]
        ).first()
        if not term:
            raise serializers.ValidationError({
                "term_id": _("Term not found or does not belong to the academic session.")
            })

        # Validate classes exist and belong to school
        classes = ClassRoom.objects.filter(
            id__in=data["class_ids"],
            school_id=data["school_id"]
        )
        if len(classes) != len(data["class_ids"]):
            raise serializers.ValidationError({
                "class_ids": _("Some classes do not exist or do not belong to the school.")
            })

        return data

    @transaction.atomic
    def create(self, validated_data):
        timetables = []
        school = School.objects.get(id=validated_data["school_id"])
        session = AcademicSession.objects.get(id=validated_data["academic_session_id"])
        term = AcademicTerm.objects.get(id=validated_data["term_id"])
        classes = ClassRoom.objects.filter(id__in=validated_data["class_ids"])

        for class_room in classes:
            timetable = Timetable.objects.create(
                school=school,
                class_room=class_room,
                timetable_type=validated_data["timetable_type"],
                name=f"{validated_data["name_prefix"]} - {class_room.name}",
                academic_session=session,
                term=term,
                start_date=validated_data["start_date"],
                end_date=validated_data["end_date"],
                is_active=False
            )
            timetables.append(timetable)

        return timetables

class TimetableEntryBulkSerializer(serializers.Serializer):
    """Serializer for bulk adding entries to a timetable"""
    timetable_id = serializers.IntegerField()
    entries = TimetableEntryCreateUpdateSerializer(many=True)

    def validate_timetable_id(self, value):
        if not Timetable.objects.filter(id=value).exists():
            raise serializers.ValidationError(_("Timetable not found."))
        return value

    @transaction.atomic
    def create(self, validated_data):
        timetable = Timetable.objects.get(id=validated_data["timetable_id"])
        created_entries = []

        for entry_data in validated_data["entries"]:
            entry_data["timetable"] = timetable
            entry_data["school"] = timetable.school
            entry_data["class_room"] = timetable.class_room
            entry = TimetableEntry.objects.create(**entry_data)
            created_entries.append(entry)

        return created_entries
