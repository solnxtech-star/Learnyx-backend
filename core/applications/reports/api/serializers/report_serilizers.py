# report/serializers.py

from core.applications.grading.api.serializers.grade_student_serializer import GradingKeySerializer
from rest_framework import serializers
from django.utils.translation import gettext_lazy as _

from core.applications.users.models import StudentProfile
from core.applications.academics.models import AcademicTerm, ClassRoom
from core.applications.grading.models import SubjectResult, TeacherComment, TermReportSummary


class StudentReportDataSerializer(serializers.Serializer):
    """
    Serializer for generating student report data.
    Combines subject results, term summary, and additional information
    needed for report generation.
    """

    student_id = serializers.IntegerField(required=True)
    term_id = serializers.IntegerField(required=True)
    include_comments = serializers.BooleanField(default=True)
    include_targets = serializers.BooleanField(default=True)
    report_type = serializers.ChoiceField(
        choices=[
            ('end_term', _('End of Term Report')),
            ('half_term', _('Half Term Progress Report')),
            ('transcript', _('Academic Transcript')),
            ('individual', _('Individual Subject Report'))
        ],
        default='end_term'
    )

    def validate(self, data):
        request = self.context['request']
        school = request.user.school

        try:
            student = StudentProfile.objects.get(id=data['student_id'], school=school)
        except StudentProfile.DoesNotExist:
            raise serializers.ValidationError({'student_id': _("Student not found in your school")})

        try:
            term = AcademicTerm.objects.get(id=data['term_id'], session__school=school)
        except AcademicTerm.DoesNotExist:
            raise serializers.ValidationError({'term_id': _("Academic term not found in your school")})

        if not SubjectResult.objects.filter(student=student, term=term).exists():
            raise serializers.ValidationError({
                'student_id': _("No results found for this student in the selected term")
            })

        data['student'] = student
        data['term'] = term
        return data


class SubjectResultReportSerializer(serializers.ModelSerializer):
    """
    Serializer for subject results in report format.
    Includes all information needed for displaying on report sheets.
    """

    subject_name = serializers.CharField(source='classroom_subject.subject.name', read_only=True)
    subject_code = serializers.CharField(source='classroom_subject.subject.code', read_only=True)
    teacher_comments = serializers.SerializerMethodField()

    class Meta:
        model = SubjectResult
        fields = [
            'subject_name', 'subject_code', 'total_ca', 'exam_score',
            'half_term_score', 'total_score', 'average_score', 'grade',
            'grade_point', 'remark', 'teacher_comments', 'target_grade',
            'target_point', 'subject_position'
        ]

    def get_teacher_comments(self, obj):
        comments = TeacherComment.objects.filter(
            subject_result=obj, is_visible_to_parents=True
        ).order_by('comment_type')

        return [
            {
                'type': c.get_comment_type_display(),
                'comment': c.comment,
                'teacher': c.teacher.get_full_name() if c.teacher else None
            }
            for c in comments
        ]


class TermReportSummarySerializer(serializers.ModelSerializer):
    """
    Serializer for term report summary in report format.
    Includes overall performance metrics for the term.
    """

    student_name = serializers.CharField(source='student.get_full_name', read_only=True)
    student_id = serializers.CharField(source='student.student_id', read_only=True)
    class_name = serializers.SerializerMethodField()

    class Meta:
        model = TermReportSummary
        fields = [
            'student_name', 'student_id', 'class_name', 'total_score',
            'average_score', 'total_points', 'gpa', 'target_gpa',
            'target_total_points', 'class_position', 'attendance_percentage',
            'conduct_rating', 'principal_comment', 'form_teacher_comment'
        ]

    def get_class_name(self, obj):
        if obj.student.class_room:
            return f"{obj.student.class_room.academic_class} {obj.student.class_room.arm}"
        return ""


class BulkReportGenerationSerializer(serializers.Serializer):
    """
    Serializer for bulk report generation.
    Allows generating reports for multiple students or classes.
    """

    term_id = serializers.IntegerField(required=True)
    class_room_ids = serializers.ListField(child=serializers.IntegerField(), required=False)
    student_ids = serializers.ListField(child=serializers.IntegerField(), required=False)
    report_type = serializers.ChoiceField(
        choices=[('end_term', _('End of Term Report')), ('half_term', _('Half Term'))],
        default='end_term'
    )
    format = serializers.ChoiceField(choices=[('pdf', 'PDF'), ('html', 'HTML'), ('json', 'JSON')], default='pdf')
    include_summary = serializers.BooleanField(default=True)
    include_grading_key = serializers.BooleanField(default=True)

    def validate(self, data):
        request = self.context['request']
        school = request.user.school

        try:
            term = AcademicTerm.objects.get(id=data['term_id'], session__school=school)
        except AcademicTerm.DoesNotExist:
            raise serializers.ValidationError({'term_id': _("Academic term not found in your school")})

        class_room_ids = data.get('class_room_ids', [])
        if class_room_ids:
            valid = ClassRoom.objects.filter(id__in=class_room_ids, school=school).values_list('id', flat=True)
            invalid = set(class_room_ids) - set(valid)
            if invalid:
                raise serializers.ValidationError({'class_room_ids': _("Invalid classroom IDs: %s" % ', '.join(map(str, invalid)))})

        student_ids = data.get('student_ids', [])
        if student_ids:
            valid = StudentProfile.objects.filter(id__in=student_ids, school=school).values_list('id', flat=True)
            invalid = set(student_ids) - set(valid)
            if invalid:
                raise serializers.ValidationError({'student_ids': _("Invalid student IDs: %s" % ', '.join(map(str, invalid)))})

        if not class_room_ids and not student_ids:
            raise serializers.ValidationError({'non_field_errors': _("Provide class_room_ids or student_ids")})

        data['term'] = term
        return data


class ReportPreviewSerializer(serializers.Serializer):
    """
    Serializer for report preview page.
    """
    school_info = serializers.DictField()
    student_info = serializers.DictField()
    report_period = serializers.DictField()
    subject_results = SubjectResultReportSerializer(many=True)
    term_summary = TermReportSummarySerializer()
    grading_key = GradingKeySerializer(many=True, required=False)
    teacher_comments = serializers.ListField(child=serializers.DictField(), required=False)
    signatures = serializers.DictField(required=False)
    report_metadata = serializers.DictField(required=False)


class ReportStatusSerializer(serializers.Serializer):
    """
    Serializer for report generation status tracking.
    """

    task_id = serializers.CharField()
    status = serializers.ChoiceField(choices=[
        ('pending', _('Pending')),
        ('processing', _('Processing')),
        ('completed', _('Completed')),
        ('failed', _('Failed')),
    ])
    progress = serializers.IntegerField(min_value=0, max_value=100)
    total_reports = serializers.IntegerField(min_value=0, required=False)
    completed_reports = serializers.IntegerField(min_value=0, required=False)
    estimated_time = serializers.IntegerField(min_value=0, required=False)
    download_url = serializers.CharField(required=False, allow_blank=True)
    error_message = serializers.CharField(required=False, allow_blank=True, allow_null=True)

    def validate(self, data):
        status = data.get('status')
        progress = data.get('progress', 0)

        if status == 'completed' and progress < 100:
            raise serializers.ValidationError({'progress': _("Progress must be 100% when completed")})

        if status == 'failed' and progress > 0:
            raise serializers.ValidationError({'progress': _("Progress must be 0 when failed")})

        total = data.get('total_reports')
        done = data.get('completed_reports')

        if total is not None and done is not None:
            if done > total:
                raise serializers.ValidationError({'completed_reports': _("Completed cannot exceed total")})

        download_url = data.get('download_url')
        if download_url and status != 'completed':
            raise serializers.ValidationError({'download_url': _("Download URL only allowed when completed")})

        return data
