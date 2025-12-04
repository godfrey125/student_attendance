from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.utils import timezone
from django.db.models import Count, Q
from .models import Student, FaceImage, AttendanceSession, SessionLog, Teacher, Course
from .services.face_recognition_service import FaceRecognitionService
import json

# Authentication Views
def teacher_login(request):
    """Teacher login view"""
    if request.method == 'POST':
        username = request.POST.get('username')
        password = request.POST.get('password')
        
        user = authenticate(request, username=username, password=password)
        
        if user is not None:
            # Check if user is a teacher
            try:
                teacher = Teacher.objects.get(user=user, is_active=True)
                login(request, user)
                return redirect('attendance_dashboard')
            except Teacher.DoesNotExist:
                error_message = "You do not have teacher privileges"
                return render(request, 'login.html', {'error': error_message})
        else:
            error_message = "Invalid username or password"
            return render(request, 'login.html', {'error': error_message})
    
    return render(request, 'login.html')


@login_required
def teacher_logout(request):
    """Teacher logout view"""
    logout(request)
    return redirect('teacher_login')


# Dashboard Views
@login_required
def attendance_dashboard(request):
    """Main attendance dashboard for teachers"""
    try:
        teacher = Teacher.objects.get(user=request.user)
    except Teacher.DoesNotExist:
        return redirect('teacher_login')
    
    # Get recent sessions
    recent_sessions = AttendanceSession.objects.all()[:10]
    
    # Get active session if any
    active_session = AttendanceSession.objects.filter(
        status='active',
        start_time__lte=timezone.now(),
        end_time__gte=timezone.now()
    ).first()
    
    context = {
        'teacher': teacher,
        'recent_sessions': recent_sessions,
        'active_session': active_session
    }
    
    return render(request, 'dashboard.html', context)


@login_required
def session_detail(request, session_id):
    """View detailed attendance for a specific session"""
    try:
        teacher = Teacher.objects.get(user=request.user)
    except Teacher.DoesNotExist:
        return redirect('teacher_login')
    
    session = get_object_or_404(AttendanceSession, id=session_id)
    
    # Get attendance statistics
    stats = session.get_attendance_statistics()
    
    # Get present students with their front face images
    present_students = SessionLog.objects.filter(
        session=session,
        status='present'
    ).select_related('student').order_by('recognized_at')
    
    present_list = []
    for log in present_students:
        front_image = log.student.get_front_face_image()
        present_list.append({
            'log': log,
            'student': log.student,
            'front_image': front_image,
            'confidence': log.confidence_score
        })
    
    # Get absent students
    absent_students = SessionLog.objects.filter(
        session=session,
        status='absent'
    ).select_related('student').order_by('student__last_name', 'student__first_name')
    
    context = {
        'teacher': teacher,
        'session': session,
        'stats': stats,
        'present_students': present_list,
        'absent_students': absent_students
    }
    
    return render(request, 'session_detail.html', context)


@login_required
def student_verification(request, session_id, student_id):
    """View all angle images for a student for verification purposes"""
    try:
        teacher = Teacher.objects.get(user=request.user)
    except Teacher.DoesNotExist:
        return redirect('teacher_login')
    
    session = get_object_or_404(AttendanceSession, id=session_id)
    student = get_object_or_404(Student, student_id=student_id)
    session_log = get_object_or_404(SessionLog, session=session, student=student)
    
    # Get all angle images
    angle_images = student.get_all_angles()
    
    context = {
        'teacher': teacher,
        'session': session,
        'student': student,
        'session_log': session_log,
        'angle_images': angle_images
    }
    
    return render(request, 'student_verification.html', context)


# Session Management Views
@login_required
@require_http_methods(["POST"])
def create_session(request):
    """Create a new attendance session"""
    try:
        teacher = Teacher.objects.get(user=request.user)
        
        course_code = request.POST.get('course')
        session_name = request.POST.get('session_name')
        session_date = request.POST.get('session_date')
        start_time = request.POST.get('start_time')
        end_time = request.POST.get('end_time')
        
        # Get course
        try:
            course = Course.objects.get(code=course_code)
        except Course.DoesNotExist:
            return JsonResponse({
                'success': False,
                'error': 'Invalid course selected'
            }, status=400)
        
        session = AttendanceSession.objects.create(
            session_name=session_name,
            course=course,
            session_date=session_date,
            start_time=start_time,
            end_time=end_time,
            created_by=request.user,
            status='active'
        )
        
        # Initialize session logs for all students IN THIS COURSE
        face_service = FaceRecognitionService()
        students = Student.objects.filter(is_active=True, course=course)
        
        for student in students:
            SessionLog.objects.create(
                session=session,
                student=student,
                status='absent'
            )
        
        return JsonResponse({
            'success': True,
            'session_id': session.id,
            'message': 'Session created successfully'
        })
        
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=400)


@login_required
@require_http_methods(["POST"])
def start_recognition(request, session_id):
    """Start face recognition for a session"""
    try:
        teacher = Teacher.objects.get(user=request.user)
        session = get_object_or_404(AttendanceSession, id=session_id)
        
        if not session.is_active():
            return JsonResponse({
                'success': False,
                'error': 'Session is not active'
            }, status=400)
        
        # Get camera source (default to 0 for webcam)
        camera_source = request.POST.get('camera_source', 0)
        try:
            camera_source = int(camera_source)
        except ValueError:
            pass  # Keep as string if it's a URL or file path
        
        # Start face recognition in background thread
        # Note: In production, use Celery or similar for background tasks
        face_service = FaceRecognitionService()
        
        # This is a simplified version - in production, run this asynchronously
        import threading
        recognition_thread = threading.Thread(
            target=face_service.process_video_stream,
            args=(session, camera_source)
        )
        recognition_thread.daemon = True
        recognition_thread.start()
        
        return JsonResponse({
            'success': True,
            'message': 'Face recognition started'
        })
        
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=400)


@login_required
@require_http_methods(["POST"])
def end_session(request, session_id):
    """End an attendance session"""
    try:
        teacher = Teacher.objects.get(user=request.user)
        session = get_object_or_404(AttendanceSession, id=session_id)
        
        session.status = 'completed'
        session.save()
        
        return JsonResponse({
            'success': True,
            'message': 'Session ended successfully'
        })
        
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=400)


# Student Management Views
@login_required
def students_by_course(request):
    """View students organized by course"""
    try:
        teacher = Teacher.objects.get(user=request.user)
    except Teacher.DoesNotExist:
        return redirect('teacher_login')
    
    # Get students by course
    coet_students = Student.objects.filter(course__code='COET', is_active=True).order_by('last_name', 'first_name')
    bit_students = Student.objects.filter(course__code='BIT', is_active=True).order_by('last_name', 'first_name')
    ba_students = Student.objects.filter(course__code='BA', is_active=True).order_by('last_name', 'first_name')
    
    context = {
        'teacher': teacher,
        'coet_students': coet_students,
        'bit_students': bit_students,
        'ba_students': ba_students,
        'coet_count': coet_students.count(),
        'bit_count': bit_students.count(),
        'ba_count': ba_students.count(),
        'coet_active': coet_students.count(),
        'bit_active': bit_students.count(),
        'ba_active': ba_students.count(),
    }
    
    return render(request, 'students_by_course.html', context)


@login_required
def student_list(request):
    """List all students"""
    try:
        teacher = Teacher.objects.get(user=request.user)
    except Teacher.DoesNotExist:
        return redirect('teacher_login')
    
    students = Student.objects.filter(is_active=True).order_by('last_name', 'first_name')
    
    context = {
        'teacher': teacher,
        'students': students
    }
    
    return render(request, 'student_list.html', context)


@login_required
def camera_capture(request):
    """Camera capture page for student enrollment"""
    try:
        teacher = Teacher.objects.get(user=request.user)
    except Teacher.DoesNotExist:
        return redirect('teacher_login')
    
    context = {
        'teacher': teacher
    }
    
    return render(request, 'camera_capture.html', context)


@login_required
def enroll_student(request):
    """Enroll a new student with face images"""
    try:
        teacher = Teacher.objects.get(user=request.user)
    except Teacher.DoesNotExist:
        return redirect('teacher_login')
    
    if request.method == 'POST':
        try:
            student_id = request.POST.get('student_id')
            first_name = request.POST.get('first_name')
            last_name = request.POST.get('last_name')
            email = request.POST.get('email')
            course_code = request.POST.get('course')
            
            # Debug logging
            print(f"DEBUG: Received data - ID: {student_id}, Name: {first_name} {last_name}, Email: {email}, Course: {course_code}")
            
            # Validate required fields
            if not all([student_id, first_name, last_name, email, course_code]):
                missing = []
                if not student_id: missing.append('student_id')
                if not first_name: missing.append('first_name')
                if not last_name: missing.append('last_name')
                if not email: missing.append('email')
                if not course_code: missing.append('course')
                
                return JsonResponse({
                    'success': False,
                    'error': f'Missing required fields: {", ".join(missing)}'
                }, status=400)
            
            # Check if student already exists
            if Student.objects.filter(student_id=student_id).exists():
                return JsonResponse({
                    'success': False,
                    'error': 'Student ID already exists'
                }, status=400)
            
            # Get course
            try:
                course = Course.objects.get(code=course_code)
            except Course.DoesNotExist:
                return JsonResponse({
                    'success': False,
                    'error': f'Invalid course selected: {course_code}'
                }, status=400)
            
            # Create student
            student = Student.objects.create(
                student_id=student_id,
                first_name=first_name,
                last_name=last_name,
                email=email,
                course=course
            )
            
            print(f"DEBUG: Student created: {student}")
            
            # Get uploaded images
            front_image = request.FILES.get('front_image')
            left_image = request.FILES.get('left_image')
            right_image = request.FILES.get('right_image')
            
            print(f"DEBUG: Images received - Front: {front_image}, Left: {left_image}, Right: {right_image}")
            
            if not all([front_image, left_image, right_image]):
                student.delete()
                missing_images = []
                if not front_image: missing_images.append('front_image')
                if not left_image: missing_images.append('left_image')
                if not right_image: missing_images.append('right_image')
                
                return JsonResponse({
                    'success': False,
                    'error': f'All three face angles are required. Missing: {", ".join(missing_images)}'
                }, status=400)
            
            # Save face images
            face_service = FaceRecognitionService()
            result = face_service.save_student_face_images(
                student, front_image, left_image, right_image
            )
            
            print(f"DEBUG: Face save result: {result}")
            
            if result['success']:
                return JsonResponse({
                    'success': True,
                    'student_id': student.student_id,
                    'message': 'Student enrolled successfully'
                })
            else:
                student.delete()
                return JsonResponse({
                    'success': False,
                    'error': result['errors']
                }, status=400)
        
        except Exception as e:
            print(f"ERROR in enroll_student: {str(e)}")
            import traceback
            traceback.print_exc()
            return JsonResponse({
                'success': False,
                'error': f'Server error: {str(e)}'
            }, status=400)
    
    context = {
        'teacher': teacher
    }
    
    return render(request, 'enroll_student.html', context)


@login_required
def live_attendance_session(request, session_id):
    """Live attendance session with camera"""
    try:
        teacher = Teacher.objects.get(user=request.user)
    except Teacher.DoesNotExist:
        return redirect('teacher_login')
    
    session = get_object_or_404(AttendanceSession, id=session_id)
    total_students = Student.objects.filter(is_active=True, course=session.course).count()
    
    context = {
        'teacher': teacher,
        'session': session,
        'total_students': total_students
    }
    
    return render(request, 'live_attendance.html', context)


@require_http_methods(["POST"])
def recognize_face_api(request):
    """API endpoint for real-time face recognition"""
    try:
        if 'image' not in request.FILES:
            return JsonResponse({
                'success': False,
                'error': 'No image provided'
            })
        
        session_id = request.POST.get('session_id')
        if not session_id:
            return JsonResponse({
                'success': False,
                'error': 'No session ID provided'
            })
        
        session = get_object_or_404(AttendanceSession, id=session_id)
        image_file = request.FILES['image']
        
        # Save temporary file
        import tempfile
        import os
        
        with tempfile.NamedTemporaryFile(delete=False, suffix='.jpg') as temp_file:
            for chunk in image_file.chunks():
                temp_file.write(chunk)
            temp_path = temp_file.name
        
        try:
            # Initialize face recognition service
            face_service = FaceRecognitionService()
            
            # Load known faces from the session's course ONLY
            known_encodings, known_student_ids = face_service.load_known_faces(course=session.course)
            
            if len(known_encodings) == 0:
                return JsonResponse({
                    'success': False,
                    'error': f'No enrolled students found for {session.course.code}',
                    'faces_detected': 0
                })
            
            # Load and process image
            import face_recognition
            import cv2
            
            frame = cv2.imread(temp_path)
            if frame is None:
                return JsonResponse({
                    'success': False,
                    'error': 'Could not read image',
                    'faces_detected': 0
                })
            
            # Recognize face
            student_id, confidence = face_service.recognize_face_from_frame(
                frame, known_encodings, known_student_ids
            )
            
            # Count faces in frame
            rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            face_locations = face_recognition.face_locations(rgb_frame)
            faces_detected = len(face_locations)
            
            if student_id:
                # Verify student is in this session's course
                student = Student.objects.get(student_id=student_id)
                if student.course != session.course:
                    # Student not in this course, ignore
                    return JsonResponse({
                        'success': True,
                        'student': None,
                        'faces_detected': faces_detected,
                        'message': 'Student not enrolled in this course'
                    })
                
                # Mark attendance
                session_log = face_service.mark_attendance(
                    session, student_id, confidence, frame
                )
                
                if session_log:
                    return JsonResponse({
                        'success': True,
                        'student': {
                            'student_id': student_id,
                            'name': student.full_name,
                            'confidence': confidence,
                            'course': student.course.code
                        },
                        'faces_detected': faces_detected
                    })
            
            return JsonResponse({
                'success': True,
                'student': None,
                'faces_detected': faces_detected
            })
            
        finally:
            # Clean up temp file
            if os.path.exists(temp_path):
                os.remove(temp_path)
    
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e),
            'faces_detected': 0
        })


# API Endpoints for AJAX requests
@login_required
def get_session_statistics(request, session_id):
    """Get real-time statistics for a session"""
    session = get_object_or_404(AttendanceSession, id=session_id)
    stats = session.get_attendance_statistics()
    
    return JsonResponse({
        'success': True,
        'statistics': stats
    })


@login_required
def get_present_students(request, session_id):
    """Get list of present students for a session"""
    session = get_object_or_404(AttendanceSession, id=session_id)
    
    present_students = SessionLog.objects.filter(
        session=session,
        status='present'
    ).select_related('student').order_by('-recognized_at')
    
    students_data = []
    for log in present_students:
        front_image = log.student.get_front_face_image()
        students_data.append({
            'student_id': log.student.student_id,
            'name': log.student.full_name,
            'recognized_at': log.recognized_at.strftime('%Y-%m-%d %H:%M:%S'),
            'confidence': log.confidence_score,
            'front_image_url': front_image.image.url if front_image else None
        })
    
    return JsonResponse({
        'success': True,
        'students': students_data
    })