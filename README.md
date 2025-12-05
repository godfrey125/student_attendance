cat > README.md << 'EOF'
# AI-Powered Student Attendance System

Automatic face recognition attendance system with course management (COET, BIT, BA).

## Features
- Live camera face recognition
- Course-based student management
- Automatic attendance marking
- Real-time statistics
- Multiple camera support (USB/WiFi)

## Installation
1. Clone repository
2. Install dependencies: `pip install -r requirements.txt`
3. Run migrations: `python manage.py migrate`
4. Create courses and teacher account
5. Start server: `python manage.py runserver`

## Login
- Username: teacher
- Password: password123

## Technologies
- Django 5.2
- OpenCV
- face-recognition
- SQLite/PostgreSQL
EOF

git add README.md
git commit -m "Add README"
git push
