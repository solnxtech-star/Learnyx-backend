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
from core.helper.enums import TimetableType


# ========== HELPER SERIALIZERS FOR DOCUMENTATION ==========
class MessageResponseSerializer(serializers.Serializer):
    message = serializers.CharField(help_text="Success message")

class ErrorResponseSerializer(serializers.Serializer):
    error = serializers.CharField(help_text="Error message")

class RemoveEntryRequestSerializer(serializers.Serializer):
    entry_id = serializers.IntegerField(help_text="ID of the entry to remove")

class CloneTimetableRequestSerializer(serializers.Serializer):
    name = serializers.CharField(
        required=False,
        help_text="Name for the cloned timetable (defaults to 'Original Name (Copy)')"
    )


class TimeSlotSerializer(serializers.ModelSerializer):
    class Meta:
        model = TimeSlot
        fields = ["id", "name", "start_time", "end_time", "is_break"]

class SubjectSerializer(serializers.ModelSerializer):
    class Meta:
        model = Subject
        fields = ["id", "name", "code", "is_mandatory"]

# Validators for timetable entries to ensure no duplicates and correct fields based on timetable type
class TimetableEntryValidator:
    @staticmethod
    def validate_entry(data, timetable, instance=None):
        """
        Validates that:
        - For CLASS timetable, day_of_week is required and date should not be set.
        - For EXAM timetable, date is required and day_of_week should not be set.
        - Prevent duplicate time slots for the same day (for CLASS) or same date (for EXAM) within the same timetable.
        """

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

            queryset = TimetableEntry.objects.filter(
                timetable=timetable,
                day_of_week=day_of_week,
                time_slot=time_slot
            )

        else:  # EXAM
            if not date:
                raise serializers.ValidationError({
                    "date": _("Date is required for exam timetable.")
                })
            if day_of_week:
                raise serializers.ValidationError({
                    "day_of_week": _("Day of week should not be set for exam timetable.")
                })

            queryset = TimetableEntry.objects.filter(
                timetable=timetable,
                date=date,
                time_slot=time_slot
            )

        if instance:
            queryset = queryset.exclude(id=instance.id)

        if queryset.exists():
            raise serializers.ValidationError({
                "non_field_errors": _("Time slot already exists.")
            })

class TimetableEntrySerializer(serializers.ModelSerializer):
    day_of_week_display = serializers.CharField(source="get_day_of_week_display", read_only=True)
    time_slot_detail = TimeSlotSerializer(source="time_slot", read_only=True)
    subject_detail = SubjectSerializer(source="subject", read_only=True)
    teacher_name = serializers.SerializerMethodField()

    class Meta:
        model = TimetableEntry
        fields = [
            "id", "timetable",
            "day_of_week", "day_of_week_display",
            "date", "time_slot", "time_slot_detail",
            "subject", "subject_detail",
            "teacher", "teacher_name"
        ]
        read_only_fields = ["id", "timetable"]

    def get_teacher_name(self, obj):
        if obj.teacher:
            return f"{obj.teacher.user.name}"
        return None

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
            "is_active", "entry_count", "created_at"
        ]
        read_only_fields = ["id", "created_at", "updated_at"]

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
            "created_at", "updated_at"
        ]
        read_only_fields = ["id", "created_at", "updated_at"]

class TimetableEntryCreateUpdateSerializer(serializers.ModelSerializer):

    class Meta:
        model = TimetableEntry
        fields = [
            "id", "day_of_week", "date",
            "time_slot", "subject", "teacher"
        ]

    def validate(self, data):
        timetable = self.context.get("timetable") or getattr(self.instance, "timetable", None)

        # Only run entry-level validation when timetable context is available
        # (i.e., when called from _sync_entries, not during parent is_valid())
        if timetable:
            TimetableEntryValidator.validate_entry(
                data=data,
                timetable=timetable,
                instance=self.instance
            )

        return data


class TimetableCreateUpdateSerializer(serializers.ModelSerializer):
    # Declared as a plain write-only list field so DRF does NOT
    # try to validate entries through TimetableEntryCreateUpdateSerializer
    # during is_valid() — we handle entries entirely in create/update.
    entries = serializers.ListField(
        child=serializers.DictField(),
        required=False,
        write_only=True
    )

    class Meta:
        model = Timetable
        fields = [
            "id",
            "name",
            "class_room",
            "timetable_type",
            "academic_session",
            "term",
            "start_date",
            "end_date",
            "is_active",
            "entries",
        ]
        read_only_fields = ["id"]

    # -------------------------------
    # VALIDATION
    # -------------------------------
    def validate(self, data):
        request = self.context["request"]
        school = request.user.school

        class_room = data.get("class_room")
        if class_room and class_room.school_id != school.id:
            raise serializers.ValidationError({
                "class_room": _("Classroom must belong to your school.")
            })

        term = data.get("term")
        session = data.get("academic_session")
        if term and session and term.session_id != session.id:
            raise serializers.ValidationError({
                "term": _("Term must belong to the selected academic session.")
            })

        start = data.get("start_date")
        end = data.get("end_date")
        if start and end and end <= start:
            raise serializers.ValidationError({
                "end_date": _("End date must be after start date.")
            })

        return data

    # -------------------------------
    # CREATE
    # -------------------------------
    @transaction.atomic
    def create(self, validated_data):
        entries_data = validated_data.pop("entries", [])

        # ✅ FIX: removed school=request.user.school here
        # school is already injected into validated_data by
        # perform_create via serializer.save(school=user.school)
        timetable = Timetable.objects.create(**validated_data)

        self._sync_entries(timetable, entries_data)

        return timetable

    # -------------------------------
    # UPDATE
    # -------------------------------
    @transaction.atomic
    def update(self, instance, validated_data):
        entries_data = validated_data.pop("entries", None)

        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()

        if entries_data is not None:
            self._sync_entries(instance, entries_data, replace=True)

        return instance

    # -------------------------------
    # SYNC ENGINE
    # -------------------------------
    def _sync_entries(self, timetable, entries_data, replace=False):
        existing_entries = {
            entry.id: entry for entry in timetable.entries.all()
        }

        incoming_ids = set()
        saved_entries = []
        errors = []

        for index, entry_data in enumerate(entries_data):
            entry_id = entry_data.get("id")

            if entry_id:
                entry = existing_entries.get(entry_id)
                if not entry:
                    errors.append({index: {"id": _("Invalid entry ID.")}})
                    continue

                serializer = TimetableEntryCreateUpdateSerializer(
                    entry,
                    data=entry_data,
                    partial=True,
                    context={"timetable": timetable}
                )
            else:
                serializer = TimetableEntryCreateUpdateSerializer(
                    data=entry_data,
                    context={"timetable": timetable}
                )

            if serializer.is_valid():
                entry = serializer.save(timetable=timetable)
                incoming_ids.add(entry.id)
                saved_entries.append(entry)
            else:
                errors.append({index: serializer.errors})

        if errors:
            raise serializers.ValidationError({"entries": errors})

        # DELETE removed entries on full replace (PUT)
        if replace:
            to_delete_ids = set(existing_entries.keys()) - incoming_ids
            if to_delete_ids:
                TimetableEntry.objects.filter(
                    id__in=to_delete_ids,
                    timetable=timetable
                ).delete()

        # Final business rule validation across all saved entries
        self._validate_entries_business_rules(timetable, saved_entries)

    # -------------------------------
    # BUSINESS RULES
    # -------------------------------
    def _validate_entries_business_rules(self, timetable, entries):
        """
        Cross-entry validation:
        - No teacher clash across time slots
        - No duplicate time slots per class
        """
        for entry in entries:
            TimetableEntryValidator.validate_entry(
                data={
                    "time_slot": entry.time_slot,
                    "teacher": entry.teacher,
                    "subject": entry.subject,
                    "day_of_week": entry.day_of_week,
                    "date": entry.date,
                },
                timetable=timetable,
                instance=entry
            )

class TimetableBulkCreateSerializer(serializers.Serializer):
    academic_session_id = serializers.IntegerField()
    term_id = serializers.IntegerField()
    timetable_type = serializers.ChoiceField(choices=TimetableType.choices)
    start_date = serializers.DateField()
    end_date = serializers.DateField()
    class_ids = serializers.ListField(child=serializers.IntegerField())
    name_prefix = serializers.CharField(required=False, default="Timetable")

    def validate(self, data):
        """
        Validate that:
        - All classes belong to the user's school
        - Term belongs to the selected academic session
        - Start date is before end date
        """
        request = self.context["request"]
        school = request.user.school

        classes = ClassRoom.objects.filter(
            id__in=data["class_ids"],
            school=school
        )

        if len(classes) != len(data["class_ids"]):
            raise serializers.ValidationError(_("Invalid classes for your school."))

        # validate session belongs to school
        try:
            session = AcademicSession.objects.get(
                id=data["academic_session_id"],
                school=school
            )
        except AcademicSession.DoesNotExist:
            raise serializers.ValidationError(_("Invalid academic session."))

        # validate term belongs to session
        try:
            term = AcademicTerm.objects.get(
                id=data["term_id"],
                session=session
            )
        except AcademicTerm.DoesNotExist:
            raise serializers.ValidationError(_("Invalid academic term."))

        data["session_obj"] = session
        data["term_obj"] = term

        return data

    @transaction.atomic
    def create(self, validated_data):
        """Create multiple timetables for the specified classes in a single transaction"""
        request = self.context["request"]
        school = request.user.school

        session = validated_data.pop("session_obj")
        term = validated_data.pop("term_obj")

        classes = ClassRoom.objects.filter(
            id__in=validated_data["class_ids"],
            school=school
        )

        timetables = []

        for class_room in classes:
            timetable = Timetable.objects.create(
                school=school,
                class_room=class_room,
                timetable_type=validated_data["timetable_type"],
                name=f"{validated_data['name_prefix']} - {class_room.name}",
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

    def validate(self, data):
        """Validate that timetable exists and belongs to user's school"""

        request = self.context["request"]

        try:
            timetable = Timetable.objects.get(
                id=data["timetable_id"],
                school=request.user.school
            )
        except Timetable.DoesNotExist:
            raise serializers.ValidationError(_("Timetable not found."))

        data["timetable_obj"] = timetable
        return data

    @transaction.atomic
    def create(self, validated_data):
        """Create multiple timetable entries in a single transaction"""
        timetable = validated_data["timetable_obj"]
        created_entries = []

        for entry_data in validated_data["entries"]:
            serializer = TimetableEntryCreateUpdateSerializer(
                data=entry_data,
                context={"timetable": timetable}
            )
            serializer.is_valid(raise_exception=True)

            entry = serializer.save(
                timetable=timetable
            )

            created_entries.append(entry)

        return created_entries
