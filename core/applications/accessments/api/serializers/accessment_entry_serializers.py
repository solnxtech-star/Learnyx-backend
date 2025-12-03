from rest_framework import serializers
from django.db import transaction
from django.utils.translation import gettext_lazy as _
from core.applications.academics.models import ClassRoom
from core.applications.accessments.models import AssessmentRecord, AssessmentType
from core.applications.timetable.models import Subject
from core.applications.users.models import StudentProfile


class AssessmentRecordSerializer(serializers.ModelSerializer):
    """
    Serializer for AssessmentRecord model.
    Stores actual recorded scores per student per assessment instance.

    Example:
        Student: Chinonso Ahamedula (EQHS2020-0062)
        Subject: Mathematics
        Assessment: Test 1
        Score: 18.5/20

    Attributes:
        student_name (str): Read-only field showing student's full name
        student_id (str): Read-only field showing student ID
        subject_name (str): Read-only field showing subject name
        assessment_type_name (str): Read-only field showing assessment type
        percentage_score (float): Read-only field showing calculated percentage
    """

    student_name = serializers.CharField(
        source='student.get_full_name',
        read_only=True,
        help_text=_("Student's full name")
    )
    student_id = serializers.CharField(
        source='student.student_id',
        read_only=True,
        help_text=_("Student's unique ID")
    )
    subject_name = serializers.CharField(
        source='classroom_subject.subject.name',
        read_only=True,
        help_text=_("Subject name")
    )
    assessment_type_name = serializers.CharField(
        source='assessment_type.name',
        read_only=True,
        help_text=_("Assessment type name")
    )
    percentage_score = serializers.FloatField(
        read_only=True,
        help_text=_("Calculated percentage score (score/max_possible_score * 100)")
    )

    class Meta:
        model = AssessmentRecord
        fields = [
            'id', 'student', 'student_name', 'student_id',
            'classroom_subject', 'subject_name', 'assessment_type',
            'assessment_type_name', 'index', 'score', 'max_possible_score',
            'percentage_score', 'created_at', 'updated_at'
        ]
        read_only_fields = [
            'id', 'percentage_score', 'created_at', 'updated_at'
        ]

    def validate(self, data):
        """
        Validate assessment record data.

        Ensures:
        1. Student belongs to the correct classroom
        2. Index doesn't exceed assessment type count
        3. Score doesn't exceed max possible score

        Args:
            data (dict): The assessment record data to validate

        Returns:
            dict: Validated data

        Raises:
            serializers.ValidationError: If validation fails
        """
        student = data.get('student')
        classroom_subject = data.get('classroom_subject')
        assessment_type = data.get('assessment_type')
        index = data.get('index')
        score = data.get('score')

        # Check if student belongs to the classroom
        if student and classroom_subject:
            if student.class_room != classroom_subject.class_room:
                raise serializers.ValidationError({
                    'student': _(
                        "Student %(student)s is not enrolled in %(classroom)s"
                    ) % {
                        'student': student.get_full_name(),
                        'classroom': classroom_subject.class_room
                    }
                })

        # Check index doesn't exceed assessment type count
        if assessment_type and index:
            if index > assessment_type.count:
                raise serializers.ValidationError({
                    'index': _(
                        "Index %(index)d exceeds maximum count of %(count)d for %(type)s"
                    ) % {
                        'index': index,
                        'count': assessment_type.count,
                        'type': assessment_type.name
                    }
                })

        # Check score doesn't exceed max possible score
        if score is not None:
            max_possible_score = data.get('max_possible_score', assessment_type.max_score if assessment_type else 100)
            if score > max_possible_score:
                raise serializers.ValidationError({
                    'score': _(
                        "Score %(score).2f exceeds maximum possible score of %(max).2f"
                    ) % {'score': score, 'max': max_possible_score}
                })

        return data

    def create(self, validated_data):
        """
        Create assessment record and calculate percentage score.

        Args:
            validated_data (dict): Validated serializer data

        Returns:
            AssessmentRecord: Created assessment record
        """
        # Calculate percentage score before saving
        score = validated_data.get('score')
        max_possible_score = validated_data.get('max_possible_score', 100)

        if score is not None and max_possible_score > 0:
            validated_data['percentage_score'] = (score / max_possible_score) * 100

        return super().create(validated_data)


class AssessmentEntryFormDataSerializer(serializers.Serializer):
    """
    Serializer for retrieving data needed for assessment entry form.
    Used by frontend to populate dropdowns and student lists.

    Returns:
        - Classroom information
        - Subject information
        - List of students in classroom
        - Available assessment types
        - Current active term
    """

    class_room_id = serializers.IntegerField(
        required=True,
        help_text=_("ID of the classroom for assessment entry")
    )
    subject_id = serializers.IntegerField(
        required=True,
        help_text=_("ID of the subject for assessment entry")
    )

    def validate(self, data):
        """
        Validate that classroom and subject belong to user's school.

        Args:
            data (dict): The serializer data to validate

        Returns:
            dict: Validated data with classroom and subject instances

        Raises:
            serializers.ValidationError: If validation fails
        """
        request = self.context['request']
        school = request.user.school

        # Get classroom
        try:
            class_room = ClassRoom.objects.get(
                id=data['class_room_id'],
                school=school
            )
        except ClassRoom.DoesNotExist:
            raise serializers.ValidationError({
                'class_room_id': _("Classroom not found in your school")
            })

        # Get subject
        try:
            subject = Subject.objects.get(
                id=data['subject_id'],
                school=school,
                is_active=True
            )
        except Subject.DoesNotExist:
            raise serializers.ValidationError({
                'subject_id': _("Subject not found or inactive in your school")
            })

        data['class_room'] = class_room
        data['subject'] = subject

        return data


class StudentScoreEntrySerializer(serializers.Serializer):
    """
    Serializer for individual student score entry.
    Used in bulk entry to validate each student's score.

    Example:
        {"student_id": 1, "score": 18.5, "max_possible_score": 20}
    """

    student_id = serializers.IntegerField(
        required=True,
        help_text=_("ID of the student")
    )
    score = serializers.FloatField(
        required=True,
        min_value=0,
        help_text=_("Score obtained by the student")
    )
    max_possible_score = serializers.FloatField(
        required=False,
        min_value=0,
        default=None,
        help_text=_("Maximum possible score for this assessment")
    )

    def validate(self, data):
        """
        Validate student score data.

        Args:
            data (dict): The student score data to validate

        Returns:
            dict: Validated data
        """
        # Ensure score is not negative
        if data['score'] < 0:
            raise serializers.ValidationError({
                'score': _("Score cannot be negative")
            })

        # If max_possible_score is provided, ensure score doesn't exceed it
        max_score = data.get('max_possible_score')
        if max_score is not None and data['score'] > max_score:
            raise serializers.ValidationError({
                'score': _("Score cannot exceed maximum possible score")
            })

        return data


class BulkAssessmentEntrySerializer(serializers.Serializer):
    """
    Serializer for bulk entering assessment scores.
    Allows teachers/admins to enter scores for multiple students at once.

    Example:
        {
            "classroom_subject_id": 1,
            "assessment_type_id": 1,
            "index": 1,
            "entries": [
                {"student_id": 1, "score": 18.5},
                {"student_id": 2, "score": 16.0},
                ...
            ]
        }
    """

    classroom_subject_id = serializers.IntegerField(
        required=True,
        help_text=_("ID of the classroom-subject combination")
    )
    assessment_type_id = serializers.IntegerField(
        required=True,
        help_text=_("ID of the assessment type")
    )
    index = serializers.IntegerField(
        required=True,
        min_value=1,
        help_text=_("Assessment instance number (e.g., 1 for Test 1, 2 for Test 2)")
    )
    entries = serializers.ListField(
        child=StudentScoreEntrySerializer(),
        min_length=1,
        help_text=_("List of student scores to enter")
    )

    def validate(self, data):
        """
        Validate bulk assessment entry data.

        Ensures:
        1. Classroom-subject exists and belongs to school
        2. Assessment type exists and belongs to school
        3. Index doesn't exceed assessment type count
        4. All students belong to the classroom

        Args:
            data (dict): The bulk entry data to validate

        Returns:
            dict: Validated data

        Raises:
            serializers.ValidationError: If validation fails
        """
        request = self.context['request']
        school = request.user.school

        # Import here to avoid circular imports
        from core.applications.timetable.models import ClassroomSubject

        # Get classroom-subject
        try:
            classroom_subject = ClassroomSubject.objects.get(
                id=data['classroom_subject_id'],
                class_room__school=school
            )
        except ClassroomSubject.DoesNotExist:
            raise serializers.ValidationError({
                'classroom_subject_id': _("Classroom-subject combination not found")
            })

        # Get assessment type
        try:
            assessment_type = AssessmentType.objects.get(
                id=data['assessment_type_id'],
                policy__school=school
            )
        except AssessmentType.DoesNotExist:
            raise serializers.ValidationError({
                'assessment_type_id': _("Assessment type not found")
            })

        # Validate index
        if data['index'] > assessment_type.count:
            raise serializers.ValidationError({
                'index': _(
                    "Index %(index)d exceeds maximum count of %(count)d"
                ) % {'index': data['index'], 'count': assessment_type.count}
            })

        # Validate all students belong to the classroom
        student_ids = [entry['student_id'] for entry in data['entries']]
        valid_students = StudentProfile.objects.filter(
            id__in=student_ids,
            class_room=classroom_subject.class_room,
            school=school
        ).values_list('id', flat=True)

        invalid_students = set(student_ids) - set(valid_students)
        if invalid_students:
            raise serializers.ValidationError({
                'entries': _(
                    "The following students are not enrolled in %(classroom)s: %(students)s"
                ) % {
                    'classroom': classroom_subject.class_room,
                    'students': ', '.join(map(str, invalid_students))
                }
            })

        data['classroom_subject'] = classroom_subject
        data['assessment_type'] = assessment_type

        return data

    @transaction.atomic
    def create(self, validated_data):
        """
        Create multiple assessment records in a single transaction.

        Args:
            validated_data (dict): Validated bulk entry data

        Returns:
            dict: Dictionary containing created records and statistics

        Raises:
            serializers.ValidationError: If any record creation fails
        """
        classroom_subject = validated_data['classroom_subject']
        assessment_type = validated_data['assessment_type']
        index = validated_data['index']

        created_records = []
        errors = []

        for entry in validated_data['entries']:
            try:
                # Use max_possible_score from assessment type if not specified
                max_possible_score = entry.get(
                    'max_possible_score',
                    assessment_type.max_score
                )

                # Create or update assessment record
                record, created = AssessmentRecord.objects.update_or_create(
                    student_id=entry['student_id'],
                    classroom_subject=classroom_subject,
                    assessment_type=assessment_type,
                    index=index,
                    defaults={
                        'score': entry['score'],
                        'max_possible_score': max_possible_score
                    }
                )

                created_records.append(record)

            except Exception as e:
                errors.append({
                    'student_id': entry['student_id'],
                    'error': str(e),
                    'score': entry['score']
                })

        # If there were errors, raise them with partial success information
        if errors:
            raise serializers.ValidationError({
                'message': _(
                    "Created %(success)d records with %(errors)d errors"
                ) % {'success': len(created_records), 'errors': len(errors)},
                'created_records': AssessmentRecordSerializer(created_records, many=True).data,
                'errors': errors
            })

        return {
            'message': _("Successfully created %(count)d assessment records") %
                     {'count': len(created_records)},
            'records': AssessmentRecordSerializer(created_records, many=True).data,
            'count': len(created_records)
        }
