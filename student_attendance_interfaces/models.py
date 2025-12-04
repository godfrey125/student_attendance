from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone
import os

def student_image_path(instance, filename):
    """Generate file path for student face images"""
    ext = filename.split('.')[-1]
    angle = instance.angle
    filename = f"{instance.student.student_id}_{angle}_{timezone.now().strftime('%Y%m%d_%H%M%S')}.{ext}"
    return os.path.join('face_images', str(instance.student.student_id), filename)


class Course(models.Model):
    """Course/Program model"""
    COURSE_CHOICES = [
        ('COET', 'Computer Engineering and IT'),
        ('BIT', 'Business Information Technology'),
        ('BA', 'Business Administration')
    ]
    
    code = models.CharField(max_length=10, choices=COURSE_CHOICES, unique=True, primary_key=True)
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = 'courses'
        ordering = ['code']
    
    def __str__(self):
        return f"{self.code} - {self.name}"
    
    def get_student_count(self):
        return self.students.filter(is_active=True).count()


class Student(models.Model):
    """Student model for storing student information"""
    student_id = models.CharField(max_length=50, unique=True, primary_key=True)
    first_name = models.CharField(max_length=100)
    last_name = models.CharField(max_length=100)
    email = models.EmailField(unique=True)
    course = models.ForeignKey(Course, on_delete=models.PROTECT, related_name='students')
    enrollment_date = models.DateField(auto_now_add=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'students'
        ordering = ['course', 'last_name', 'first_name']

    def __str__(self):
        return f"{self.student_id} - {self.first_name} {self.last_name} ({self.course.code})"

    @property
    def full_name(self):
        return f"{self.first_name} {self.last_name}"

    def get_front_face_image(self):
        """Get the most recent front face image"""
        return self.face_images.filter(angle='front', is_active=True).order_by('-captured_at').first()

    def get_all_angles(self):
        """Get all angle images for verification"""
        return {
            'front': self.face_images.filter(angle='front', is_active=True).order_by('-captured_at').first(),
            'left': self.face_images.filter(angle='left', is_active=True).order_by('-captured_at').first(),
            'right': self.face_images.filter(angle='right', is_active=True).order_by('-captured_at').first()
        }


class FaceImage(models.Model):
    """Store multiple face angles for each student"""
    ANGLE_CHOICES = [
        ('front', 'Front Face'),
        ('left', 'Left Side'),
        ('right', 'Right Side')
    ]

    id = models.AutoField(primary_key=True)
    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name='face_images')
    angle = models.CharField(max_length=10, choices=ANGLE_CHOICES)
    image = models.ImageField(upload_to=student_image_path)
    face_encoding = models.BinaryField(null=True, blank=True)
    captured_at = models.DateTimeField(auto_now_add=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = 'face_images'
        ordering = ['-captured_at']
        indexes = [
            models.Index(fields=['student', 'angle', 'is_active']),
            models.Index(fields=['angle']),
        ]

    def __str__(self):
        return f"{self.student.student_id} - {self.angle} - {self.captured_at}"


class AttendanceSession(models.Model):
    """Track attendance sessions"""
    SESSION_STATUS = [
        ('active', 'Active'),
        ('completed', 'Completed'),
        ('cancelled', 'Cancelled')
    ]

    id = models.AutoField(primary_key=True)
    session_name = models.CharField(max_length=200)
    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name='sessions')
    session_date = models.DateField(default=timezone.now)
    start_time = models.DateTimeField()
    end_time = models.DateTimeField()
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='sessions_created')
    status = models.CharField(max_length=20, choices=SESSION_STATUS, default='active')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'attendance_sessions'
        ordering = ['-session_date', '-start_time']

    def __str__(self):
        return f"{self.session_name} - {self.course.code} - {self.session_date}"

    def is_active(self):
        """Check if session is currently active"""
        now = timezone.now()
        return self.status == 'active' and self.start_time <= now <= self.end_time

    def get_attendance_statistics(self):
        """Calculate attendance statistics for this session"""
        total_students = Student.objects.filter(is_active=True, course=self.course).count()
        present_count = self.session_logs.filter(status='present').count()
        absent_count = total_students - present_count
        
        return {
            'total_students': total_students,
            'present_count': present_count,
            'absent_count': absent_count,
            'attendance_percentage': (present_count / total_students * 100) if total_students > 0 else 0
        }


class SessionLog(models.Model):
    """Log individual student attendance for each session"""
    ATTENDANCE_STATUS = [
        ('present', 'Present'),
        ('absent', 'Absent')
    ]

    id = models.AutoField(primary_key=True)
    session = models.ForeignKey(AttendanceSession, on_delete=models.CASCADE, related_name='session_logs')
    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name='attendance_logs')
    status = models.CharField(max_length=10, choices=ATTENDANCE_STATUS, default='absent')
    recognized_at = models.DateTimeField(null=True, blank=True)
    confidence_score = models.FloatField(null=True, blank=True)
    recognized_image = models.ImageField(upload_to='recognized_faces/', null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'session_logs'
        unique_together = ['session', 'student']
        ordering = ['-recognized_at']
        indexes = [
            models.Index(fields=['session', 'status']),
            models.Index(fields=['student', 'session']),
        ]

    def __str__(self):
        return f"{self.student.student_id} - {self.session.session_name} - {self.status}"

    def mark_present(self, confidence=None, image=None):
        """Mark student as present"""
        self.status = 'present'
        self.recognized_at = timezone.now()
        if confidence:
            self.confidence_score = confidence
        if image:
            self.recognized_image = image
        self.save()


class Teacher(models.Model):
    """Extended teacher profile linked to Django User"""
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='teacher_profile')
    teacher_id = models.CharField(max_length=50, unique=True)
    department = models.CharField(max_length=100, blank=True)
    phone = models.CharField(max_length=20, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'teachers'

    def __str__(self):
        return f"{self.teacher_id} - {self.user.get_full_name()}"