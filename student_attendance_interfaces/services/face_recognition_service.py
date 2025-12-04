import face_recognition
import numpy as np
import pickle
from django.core.files.base import ContentFile
from django.utils import timezone
from ..models import Student, FaceImage, AttendanceSession, SessionLog
import cv2
from io import BytesIO
from PIL import Image

class FaceRecognitionService:
    """Service for handling face recognition operations"""
    
    def __init__(self):
        self.tolerance = 0.6  # Adjust for recognition sensitivity
        self.model = 'hog'  # Use 'cnn' for better accuracy but slower performance
    
    def encode_face(self, image_path):
        """
        Generate face encoding from an image
        Returns: numpy array of face encoding or None
        """
        try:
            image = face_recognition.load_image_file(image_path)
            face_encodings = face_recognition.face_encodings(image)
            
            if len(face_encodings) > 0:
                return face_encodings[0]
            return None
        except Exception as e:
            print(f"Error encoding face: {str(e)}")
            return None
    
    def save_student_face_images(self, student, front_image, left_image, right_image):
        """
        Save all three angle images for a student
        Returns: dict with success status and created FaceImage objects
        """
        results = {'success': True, 'images': {}, 'errors': []}
        
        images_data = {
            'front': front_image,
            'left': left_image,
            'right': right_image
        }
        
        for angle, image_file in images_data.items():
            try:
                # Create FaceImage object
                face_image = FaceImage.objects.create(
                    student=student,
                    angle=angle,
                    image=image_file
                )
                
                # Generate and store face encoding
                encoding = self.encode_face(face_image.image.path)
                if encoding is not None:
                    face_image.face_encoding = pickle.dumps(encoding)
                    face_image.save()
                    results['images'][angle] = face_image
                else:
                    results['errors'].append(f"No face detected in {angle} image")
                    face_image.delete()
                    results['success'] = False
                    
            except Exception as e:
                results['errors'].append(f"Error saving {angle} image: {str(e)}")
                results['success'] = False
        
        return results
    
    def load_known_faces(self, course=None):
        """
        Load all active student face encodings
        If course is provided, only load students from that course
        Returns: tuple of (encodings list, student_ids list)
        """
        known_encodings = []
        known_student_ids = []
        
        # Get all active students with front face images
        query = FaceImage.objects.filter(
            angle='front',
            is_active=True,
            student__is_active=True
        )
        
        # Filter by course if provided
        if course:
            query = query.filter(student__course=course)
        
        face_images = query.select_related('student')
        
        for face_img in face_images:
            if face_img.face_encoding:
                try:
                    encoding = pickle.loads(face_img.face_encoding)
                    known_encodings.append(encoding)
                    known_student_ids.append(face_img.student.student_id)
                except Exception as e:
                    print(f"Error loading encoding for {face_img.student.student_id}: {str(e)}")
        
        return known_encodings, known_student_ids
    
    def recognize_face_from_frame(self, frame, known_encodings, known_student_ids):
        """
        Recognize face from a video frame
        Returns: tuple of (student_id, confidence_score) or (None, None)
        """
        try:
            # Convert BGR to RGB
            rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            
            # Find faces in the frame
            face_locations = face_recognition.face_locations(rgb_frame, model=self.model)
            face_encodings = face_recognition.face_encodings(rgb_frame, face_locations)
            
            if len(face_encodings) == 0:
                return None, None
            
            # Compare with known faces (use first detected face)
            face_encoding = face_encodings[0]
            face_distances = face_recognition.face_distance(known_encodings, face_encoding)
            
            if len(face_distances) > 0:
                best_match_index = np.argmin(face_distances)
                confidence = 1 - face_distances[best_match_index]
                
                if face_distances[best_match_index] <= self.tolerance:
                    return known_student_ids[best_match_index], confidence
            
            return None, None
            
        except Exception as e:
            print(f"Error recognizing face: {str(e)}")
            return None, None
    
    def mark_attendance(self, session, student_id, confidence, frame=None):
        """
        Mark student as present in the session
        Returns: SessionLog object or None
        """
        try:
            student = Student.objects.get(student_id=student_id)
            session_log, created = SessionLog.objects.get_or_create(
                session=session,
                student=student,
                defaults={'status': 'absent'}
            )
            
            # Save captured frame if provided
            if frame is not None:
                success, buffer = cv2.imencode('.jpg', frame)
                if success:
                    image_file = ContentFile(buffer.tobytes())
                    session_log.recognized_image.save(
                        f"{student_id}_{timezone.now().strftime('%Y%m%d_%H%M%S')}.jpg",
                        image_file,
                        save=False
                    )
            
            session_log.mark_present(confidence=confidence)
            return session_log
            
        except Student.DoesNotExist:
            print(f"Student {student_id} not found")
            return None
        except Exception as e:
            print(f"Error marking attendance: {str(e)}")
            return None
    
    def initialize_session_logs(self, session):
        """
        Create session logs for all active students (initially marked as absent)
        """
        students = Student.objects.filter(is_active=True)
        session_logs = []
        
        for student in students:
            log, created = SessionLog.objects.get_or_create(
                session=session,
                student=student,
                defaults={'status': 'absent'}
            )
            session_logs.append(log)
        
        return session_logs
    
    def process_video_stream(self, session, video_source=0):
        """
        Process video stream for face recognition
        video_source: 0 for webcam, or path to video file
        """
        # Load known faces
        known_encodings, known_student_ids = self.load_known_faces()
        
        if len(known_encodings) == 0:
            print("No known faces found in database")
            return
        
        # Initialize video capture
        cap = cv2.VideoCapture(video_source)
        
        # Dictionary to track recognized students
        recognized_students = set()
        
        print(f"Starting face recognition for session: {session.session_name}")
        
        try:
            while session.is_active():
                ret, frame = cap.read()
                if not ret:
                    break
                
                # Process every frame (can be optimized to process every nth frame)
                student_id, confidence = self.recognize_face_from_frame(
                    frame, known_encodings, known_student_ids
                )
                
                if student_id and student_id not in recognized_students:
                    # Mark attendance
                    session_log = self.mark_attendance(session, student_id, confidence, frame)
                    if session_log:
                        recognized_students.add(student_id)
                        print(f"Marked {student_id} as present (confidence: {confidence:.2f})")
                
                # Display frame (optional, remove for production)
                cv2.imshow('Attendance System', frame)
                
                # Break on 'q' key
                if cv2.waitKey(1) & 0xFF == ord('q'):
                    break
                    
        finally:
            cap.release()
            cv2.destroyAllWindows()
    
    def capture_multi_angle_images(self, video_source=0):
        """
        Capture front, left, and right face images for student enrollment
        Returns: dict with captured images or None
        """
        cap = cv2.VideoCapture(video_source)
        images = {}
        angles = ['front', 'left', 'right']
        current_angle_index = 0
        
        print("Face Capture Instructions:")
        print("1. Position face to FRONT and press SPACE")
        print("2. Turn face to LEFT and press SPACE")
        print("3. Turn face to RIGHT and press SPACE")
        print("Press Q to cancel")
        
        try:
            while current_angle_index < len(angles):
                ret, frame = cap.read()
                if not ret:
                    break
                
                current_angle = angles[current_angle_index]
                
                # Display instructions
                cv2.putText(frame, f"Position: {current_angle.upper()}", 
                           (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2)
                cv2.putText(frame, "Press SPACE to capture", 
                           (10, 70), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
                
                cv2.imshow('Capture Face Angles', frame)
                
                key = cv2.waitKey(1) & 0xFF
                
                if key == ord(' '):  # Space bar
                    # Convert frame to PIL Image
                    rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                    pil_image = Image.fromarray(rgb_frame)
                    
                    # Save to BytesIO
                    img_io = BytesIO()
                    pil_image.save(img_io, format='JPEG')
                    img_io.seek(0)
                    
                    images[current_angle] = ContentFile(img_io.read(), 
                                                       name=f'{current_angle}.jpg')
                    
                    print(f"Captured {current_angle} image")
                    current_angle_index += 1
                    
                elif key == ord('q'):  # Cancel
                    print("Capture cancelled")
                    return None
            
            return images if len(images) == 3 else None
            
        finally:
            cap.release()
            cv2.destroyAllWindows()