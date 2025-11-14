from django.db.models import Prefetch
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from drf_spectacular.utils import extend_schema, extend_schema_view

from core.applications.timetable.models import (
    Subject,
    TimeSlot,
    ClassSchedule,
    Timetable,
)
from core.applications.timetable.api.serializers import (
    SubjectSerializer,
    TimeSlotSerializer,
    ClassScheduleSerializer,
    ClassScheduleListSerializer,
    StudentTimetableSerializer,
    TimetableSerializer,
)
from core.helper.enums import UserRole


@extend_schema_view(
    list=extend_schema(description="List all subjects"),
    retrieve=extend_schema(description="Get a specific subject"),
    create=extend_schema(description="Create a new subject (Admin/Teacher only)"),
    update=extend_schema(description="Update a subject (Admin/Teacher only)"),
    partial_update=extend_schema(description="Partially update a subject (Admin/Teacher only)"),
    destroy=extend_schema(description="Delete a subject (Admin only)"),
)
class SubjectViewSet(viewsets.ModelViewSet):
    """
    ViewSet for managing subjects.
    
    Students: Read-only access
    Teachers: Can create and update
    Admins: Full CRUD access
    """
    queryset = Subject.objects.filter(is_active=True)
    serializer_class = SubjectSerializer
    permission_classes = [IsAuthenticated]
    
    def get_queryset(self):
        # All authenticated users can see active subjects
        return Subject.objects.filter(is_active=True).order_by('name')
    
    def get_permissions(self):
        # Read-only for students, write access for teachers and admins
        if self.action in ['list', 'retrieve']:
            return [IsAuthenticated()]
        return [IsAuthenticated()]
    
    def perform_create(self, serializer):
        # Only admins and teachers can create subjects
        if self.request.user.role not in [UserRole.ADMIN, UserRole.TEACHER]:
            from rest_framework.exceptions import PermissionDenied
            raise PermissionDenied("Only admins and teachers can create subjects.")
        serializer.save()
    
    def perform_update(self, serializer):
        # Only admins and teachers can update subjects
        if self.request.user.role not in [UserRole.ADMIN, UserRole.TEACHER]:
            from rest_framework.exceptions import PermissionDenied
            raise PermissionDenied("Only admins and teachers can update subjects.")
        serializer.save()
    
    def perform_destroy(self, instance):
        # Only admins can delete subjects
        if self.request.user.role != UserRole.ADMIN:
            from rest_framework.exceptions import PermissionDenied
            raise PermissionDenied("Only admins can delete subjects.")
        # Soft delete by setting is_active to False
        instance.is_active = False
        instance.save()


@extend_schema_view(
    list=extend_schema(description="List all time slots"),
    retrieve=extend_schema(description="Get a specific time slot"),
    create=extend_schema(description="Create a new time slot (Admin only)"),
    update=extend_schema(description="Update a time slot (Admin only)"),
    partial_update=extend_schema(description="Partially update a time slot (Admin only)"),
    destroy=extend_schema(description="Delete a time slot (Admin only)"),
)
class TimeSlotViewSet(viewsets.ModelViewSet):
    """
    ViewSet for managing time slots.
    
    Students/Teachers: Read-only access
    Admins: Full CRUD access
    """
    queryset = TimeSlot.objects.all()
    serializer_class = TimeSlotSerializer
    permission_classes = [IsAuthenticated]
    
    def get_queryset(self):
        return TimeSlot.objects.all().order_by('order', 'start_time')
    
    def perform_create(self, serializer):
        if self.request.user.role != UserRole.ADMIN:
            from rest_framework.exceptions import PermissionDenied
            raise PermissionDenied("Only admins can create time slots.")
        serializer.save()
    
    def perform_update(self, serializer):
        if self.request.user.role != UserRole.ADMIN:
            from rest_framework.exceptions import PermissionDenied
            raise PermissionDenied("Only admins can update time slots.")
        serializer.save()
    
    def perform_destroy(self, instance):
        if self.request.user.role != UserRole.ADMIN:
            from rest_framework.exceptions import PermissionDenied
            raise PermissionDenied("Only admins can delete time slots.")
        instance.delete()


@extend_schema_view(
    list=extend_schema(description="List all class schedules"),
    retrieve=extend_schema(description="Get a specific class schedule"),
    create=extend_schema(description="Create a new class schedule (Admin only)"),
    update=extend_schema(description="Update a class schedule (Admin only)"),
    partial_update=extend_schema(description="Partially update a class schedule (Admin only)"),
    destroy=extend_schema(description="Delete a class schedule (Admin only)"),
)
class ClassScheduleViewSet(viewsets.ModelViewSet):
    """
    ViewSet for managing class schedules.
    
    Students: Can view their class schedules only
    Teachers: Can view all schedules
    Admins: Full CRUD access
    """
    permission_classes = [IsAuthenticated]
    
    def get_queryset(self):
        user = self.request.user
        queryset = ClassSchedule.objects.select_related(
            'subject', 'teacher', 'time_slot'
        ).filter(is_active=True)
        
        # Students can only see their class schedules
        if user.role == UserRole.STUDENT:
            if hasattr(user, 'studentprofile'):
                student_class = user.studentprofile.current_class
                queryset = queryset.filter(academic_class=student_class)
            else:
                # If student profile doesn't exist, return empty queryset
                return ClassSchedule.objects.none()
        
        # Teachers can see all schedules (or optionally filter to their own)
        # Admins can see all schedules
        
        return queryset.order_by('academic_class', 'day_of_week', 'time_slot__order')
    
    def get_serializer_class(self):
        if self.action == 'list':
            return ClassScheduleListSerializer
        return ClassScheduleSerializer
    
    def perform_create(self, serializer):
        if self.request.user.role != UserRole.ADMIN:
            from rest_framework.exceptions import PermissionDenied
            raise PermissionDenied("Only admins can create class schedules.")
        serializer.save()
    
    def perform_update(self, serializer):
        if self.request.user.role != UserRole.ADMIN:
            from rest_framework.exceptions import PermissionDenied
            raise PermissionDenied("Only admins can update class schedules.")
        serializer.save()
    
    def perform_destroy(self, instance):
        if self.request.user.role != UserRole.ADMIN:
            from rest_framework.exceptions import PermissionDenied
            raise PermissionDenied("Only admins can delete class schedules.")
        instance.delete()
    
    @extend_schema(
        description="Get schedules filtered by day of week",
        parameters=[
            {
                'name': 'day',
                'required': True,
                'type': 'string',
                'description': 'Day of week (e.g., MONDAY, TUESDAY)'
            }
        ]
    )
    @action(detail=False, methods=['get'])
    def by_day(self, request):
        """Get schedules for a specific day"""
        day = request.query_params.get('day', '').upper()
        if not day:
            return Response(
                {"error": "Day parameter is required"},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        queryset = self.get_queryset().filter(day_of_week=day)
        serializer = ClassScheduleListSerializer(queryset, many=True)
        return Response(serializer.data)
    
    @extend_schema(
        description="Get schedules filtered by class",
        parameters=[
            {
                'name': 'class',
                'required': True,
                'type': 'string',
                'description': 'Academic class (e.g., Primary 1, JSS1)'
            }
        ]
    )
    @action(detail=False, methods=['get'])
    def by_class(self, request):
        """Get schedules for a specific class"""
        academic_class = request.query_params.get('class', '')
        if not academic_class:
            return Response(
                {"error": "Class parameter is required"},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Admins and teachers can view any class
        # Students can only view their own class
        if request.user.role == UserRole.STUDENT:
            if hasattr(request.user, 'studentprofile'):
                if request.user.studentprofile.current_class != academic_class:
                    from rest_framework.exceptions import PermissionDenied
                    raise PermissionDenied("You can only view your own class schedule.")
        
        queryset = self.get_queryset().filter(academic_class=academic_class)
        serializer = ClassScheduleListSerializer(queryset, many=True)
        return Response(serializer.data)


@extend_schema_view(
    list=extend_schema(description="List all timetables"),
    retrieve=extend_schema(description="Get a specific timetable"),
    create=extend_schema(description="Create a new timetable (Admin only)"),
    update=extend_schema(description="Update a timetable (Admin only)"),
    partial_update=extend_schema(description="Partially update a timetable (Admin only)"),
    destroy=extend_schema(description="Delete a timetable (Admin only)"),
)
class TimetableViewSet(viewsets.ModelViewSet):
    """
    ViewSet for managing complete timetables.
    
    Students: Can view active timetable for their class
    Teachers: Can view all timetables
    Admins: Full CRUD access
    """
    permission_classes = [IsAuthenticated]
    
    def get_queryset(self):
        queryset = Timetable.objects.prefetch_related(
            Prefetch(
                'schedules',
                queryset=ClassSchedule.objects.select_related(
                    'subject', 'teacher', 'time_slot'
                ).filter(is_active=True)
            )
        )
        
        # Students only see active timetables
        if self.request.user.role == UserRole.STUDENT:
            queryset = queryset.filter(is_active=True)
        
        return queryset.order_by('-start_date')
    
    def get_serializer_class(self):
        # Use student-specific serializer for students
        if self.request.user.role == UserRole.STUDENT and self.action in ['retrieve', 'list', 'my_timetable']:
            return StudentTimetableSerializer
        return TimetableSerializer
    
    def get_serializer_context(self):
        context = super().get_serializer_context()
        context['request'] = self.request
        return context
    
    def perform_create(self, serializer):
        if self.request.user.role != UserRole.ADMIN:
            from rest_framework.exceptions import PermissionDenied
            raise PermissionDenied("Only admins can create timetables.")
        serializer.save()
    
    def perform_update(self, serializer):
        if self.request.user.role != UserRole.ADMIN:
            from rest_framework.exceptions import PermissionDenied
            raise PermissionDenied("Only admins can update timetables.")
        serializer.save()
    
    def perform_destroy(self, instance):
        if self.request.user.role != UserRole.ADMIN:
            from rest_framework.exceptions import PermissionDenied
            raise PermissionDenied("Only admins can delete timetables.")
        instance.delete()
    
    @extend_schema(
        description="Get the current active timetable for the logged-in student",
        responses={200: StudentTimetableSerializer}
    )
    @action(detail=False, methods=['get'])
    def my_timetable(self, request):
        """Get current active timetable for the logged-in student"""
        if request.user.role != UserRole.STUDENT:
            return Response(
                {"error": "This endpoint is only for students"},
                status=status.HTTP_403_FORBIDDEN
            )
        
        if not hasattr(request.user, 'studentprofile'):
            return Response(
                {"error": "Student profile not found"},
                status=status.HTTP_404_NOT_FOUND
            )
        
        # Get active timetable
        timetable = Timetable.objects.filter(is_active=True).prefetch_related(
            Prefetch(
                'schedules',
                queryset=ClassSchedule.objects.select_related(
                    'subject', 'teacher', 'time_slot'
                ).filter(is_active=True)
            )
        ).first()
        
        if not timetable:
            return Response(
                {"error": "No active timetable found"},
                status=status.HTTP_404_NOT_FOUND
            )
        
        serializer = StudentTimetableSerializer(
            timetable,
            context={'request': request}
        )
        return Response(serializer.data)
    
    @extend_schema(
        description="Get the currently active timetable",
        responses={200: TimetableSerializer}
    )
    @action(detail=False, methods=['get'])
    def active(self, request):
        """Get the currently active timetable"""
        timetable = Timetable.objects.filter(is_active=True).prefetch_related(
            'schedules__subject',
            'schedules__teacher',
            'schedules__time_slot'
        ).first()
        
        if not timetable:
            return Response(
                {"error": "No active timetable found"},
                status=status.HTTP_404_NOT_FOUND
            )
        
        serializer = self.get_serializer(timetable)
        return Response(serializer.data)