from django.urls import path
from . import views

urlpatterns = [
    # Authentication
    path('login/', views.teacher_login, name='teacher_login'),
    path('logout/', views.teacher_logout, name='teacher_logout'),
    
    # Dashboard
    path('dashboard/', views.attendance_dashboard, name='attendance_dashboard'),
    path('', views.attendance_dashboard, name='home'),
    
    # Session Management
    path('session/create/', views.create_session, name='create_session'),
    path('session/<int:session_id>/', views.session_detail, name='session_detail'),
    path('session/<int:session_id>/live/', views.live_attendance_session, name='live_attendance_session'),
    path('session/<int:session_id>/start/', views.start_recognition, name='start_recognition'),
    path('session/<int:session_id>/end/', views.end_session, name='end_session'),
    
    # Student Management
    path('students/', views.student_list, name='student_list'),
    path('students/by-course/', views.students_by_course, name='students_by_course'),
    path('students/enroll/', views.enroll_student, name='enroll_student'),
    path('students/camera-capture/', views.camera_capture, name='camera_capture'),
    path('session/<int:session_id>/student/<str:student_id>/verify/', 
         views.student_verification, name='student_verification'),
    
    # API Endpoints
    path('api/recognize-face/', views.recognize_face_api, name='recognize_face_api'),
    path('api/session/<int:session_id>/statistics/', 
         views.get_session_statistics, name='get_session_statistics'),
    path('api/session/<int:session_id>/present/', 
         views.get_present_students, name='get_present_students'),
]