from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from datetime import datetime
from werkzeug.security import generate_password_hash, check_password_hash

db = SQLAlchemy()

class User(UserMixin, db.Model):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(256))
    role = db.Column(db.String(20), nullable=False, default='trainee') # 'admin' or 'trainee'
    department = db.Column(db.String(50), default='General')
    status = db.Column(db.String(20), default='active') # 'active' or 'inactive'
    employee_id = db.Column(db.String(50), default='EMP-001')
    force_password_change = db.Column(db.Boolean, default=False)
    
    def set_password(self, password):
        self.password_hash = generate_password_hash(password)
        
    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

class Document(db.Model):
    __tablename__ = 'documents'
    id = db.Column(db.Integer, primary_key=True)
    filename = db.Column(db.String(255), nullable=False)
    upload_date = db.Column(db.DateTime, default=datetime.utcnow)
    uploaded_by = db.Column(db.Integer, db.ForeignKey('users.id'))
    category = db.Column(db.String(100), default='General')
    description = db.Column(db.Text)
    week_number = db.Column(db.Integer, default=1)
    day_number = db.Column(db.Integer, default=1)
    module_id = db.Column(db.Integer, nullable=True)
    lesson_id = db.Column(db.Integer, nullable=True)
    version = db.Column(db.Integer, default=1)
    assigned_domain = db.Column(db.String(100), default='General')
    
    uploader = db.relationship('User', backref=db.backref('uploaded_docs', lazy=True))

class UserAssignment(db.Model):
    __tablename__ = 'user_assignments'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    document_id = db.Column(db.Integer, db.ForeignKey('documents.id'), nullable=False)
    assigned_date = db.Column(db.DateTime, default=datetime.utcnow)

    user = db.relationship('User', backref=db.backref('assignments', lazy=True))
    document = db.relationship('Document', backref=db.backref('assignments', lazy=True))

class ChatHistory(db.Model):
    __tablename__ = 'chat_history'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    question = db.Column(db.Text, nullable=False)
    ai_response = db.Column(db.Text, nullable=False)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    is_voice = db.Column(db.Boolean, default=False)

    user = db.relationship('User', backref=db.backref('chats', lazy=True, cascade="all, delete-orphan"))

class Exam(db.Model):
    __tablename__ = 'exams'
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(255), nullable=False)
    document_id = db.Column(db.Integer, db.ForeignKey('documents.id'), nullable=True)
    created_date = db.Column(db.DateTime, default=datetime.utcnow)
    questions_json = db.Column(db.Text, nullable=False) # Store questions as JSON string
    is_published = db.Column(db.Boolean, default=False)
    
    document = db.relationship('Document', backref=db.backref('exams', lazy=True))

class ExamAssignment(db.Model):
    __tablename__ = 'exam_assignments'
    id = db.Column(db.Integer, primary_key=True)
    exam_id = db.Column(db.Integer, db.ForeignKey('exams.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    assigned_date = db.Column(db.DateTime, default=datetime.utcnow)

    exam = db.relationship('Exam', backref=db.backref('assignments', lazy=True))
    user = db.relationship('User', backref=db.backref('exam_assignments', lazy=True))

class ExamResult(db.Model):
    __tablename__ = 'exam_results'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    exam_id = db.Column(db.Integer, db.ForeignKey('exams.id'), nullable=False)
    score = db.Column(db.Integer, nullable=False)
    total = db.Column(db.Integer, nullable=False)
    percentage = db.Column(db.Float, nullable=False)
    ai_feedback = db.Column(db.Text)
    completion_date = db.Column(db.DateTime, default=datetime.utcnow)

    user = db.relationship('User', backref=db.backref('exam_results', lazy=True))
    exam = db.relationship('Exam', backref=db.backref('results', lazy=True))

class Announcement(db.Model):
    __tablename__ = 'announcements'
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(255), nullable=False)
    content = db.Column(db.Text, nullable=False)
    date_posted = db.Column(db.DateTime, default=datetime.utcnow)
    created_by = db.Column(db.Integer, db.ForeignKey('users.id'))

    author = db.relationship('User', backref=db.backref('announcements', lazy=True))

class AnnouncementRead(db.Model):
    __tablename__ = 'announcement_reads'
    id = db.Column(db.Integer, primary_key=True)
    announcement_id = db.Column(db.Integer, db.ForeignKey('announcements.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    read_date = db.Column(db.DateTime, default=datetime.utcnow)


# --- LEARNING PATH SYSTEM MODELS ---

class LearningPath(db.Model):
    __tablename__ = 'learning_paths'
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(255), nullable=False)
    description = db.Column(db.Text, nullable=False)
    thumbnail = db.Column(db.String(255), default='default_course.png')
    department = db.Column(db.String(100), default='All Departments')
    difficulty = db.Column(db.String(50), default='Intermediate')
    estimated_weeks = db.Column(db.Integer, default=6)
    status = db.Column(db.String(50), default='Published') # 'Draft', 'Published', 'Archived'
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    weeks = db.relationship('Week', backref='learning_path', lazy=True, cascade="all, delete-orphan")

class Week(db.Model):
    __tablename__ = 'weeks'
    id = db.Column(db.Integer, primary_key=True)
    learning_path_id = db.Column(db.Integer, db.ForeignKey('learning_paths.id'), nullable=False)
    week_number = db.Column(db.Integer, nullable=False)
    title = db.Column(db.String(255), nullable=False)
    description = db.Column(db.Text)

    days = db.relationship('Day', backref='week', lazy=True, cascade="all, delete-orphan")

class Day(db.Model):
    __tablename__ = 'days'
    id = db.Column(db.Integer, primary_key=True)
    week_id = db.Column(db.Integer, db.ForeignKey('weeks.id'), nullable=False)
    day_number = db.Column(db.Integer, nullable=False) # 1 to 6
    title = db.Column(db.String(255), nullable=False)
    topic = db.Column(db.String(255))
    objectives = db.Column(db.Text)
    skills_covered = db.Column(db.String(255))
    day_type = db.Column(db.String(50), default='Lesson') # 'Lesson', 'Assessment', 'MockInterview'

    lessons = db.relationship('Lesson', backref='day', lazy=True, cascade="all, delete-orphan")

class Lesson(db.Model):
    __tablename__ = 'lessons'
    id = db.Column(db.Integer, primary_key=True)
    day_id = db.Column(db.Integer, db.ForeignKey('days.id'), nullable=False)
    title = db.Column(db.String(255), nullable=False)
    description = db.Column(db.Text)
    video_url = db.Column(db.String(500))
    document_id = db.Column(db.Integer, db.ForeignKey('documents.id'), nullable=True)
    duration_minutes = db.Column(db.Integer, default=30)
    reading_time_minutes = db.Column(db.Integer, default=15)

    document = db.relationship('Document', backref=db.backref('lessons', lazy=True))
    flashcards = db.relationship('Flashcard', backref='lesson', lazy=True, cascade="all, delete-orphan")

class UserLearningPathProgress(db.Model):
    __tablename__ = 'user_learning_path_progress'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    learning_path_id = db.Column(db.Integer, db.ForeignKey('learning_paths.id', ondelete='CASCADE'), nullable=False)
    current_week = db.Column(db.Integer, default=1)
    current_day = db.Column(db.Integer, default=1)
    completed_days_json = db.Column(db.Text, default='[]') # JSON array of completed day IDs
    completed_lessons_json = db.Column(db.Text, default='[]') # JSON array of completed lesson IDs
    streak_count = db.Column(db.Integer, default=1)
    last_activity = db.Column(db.DateTime, default=datetime.utcnow)

    user = db.relationship('User', backref=db.backref('path_progress', lazy=True, cascade="all, delete-orphan"))
    learning_path = db.relationship('LearningPath', backref=db.backref('trainee_progress', lazy=True))

class MockInterview(db.Model):
    __tablename__ = 'mock_interviews'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    week_id = db.Column(db.Integer, db.ForeignKey('weeks.id'), nullable=False)
    transcript_json = db.Column(db.Text, nullable=False) # Store Q&A transcript
    technical_score = db.Column(db.Float, default=0.0)
    communication_score = db.Column(db.Float, default=0.0)
    confidence_score = db.Column(db.Float, default=0.0)
    overall_rating = db.Column(db.Float, default=0.0)
    feedback = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    user = db.relationship('User', backref=db.backref('mock_interviews', lazy=True))
    week = db.relationship('Week', backref=db.backref('interviews', lazy=True))

class Flashcard(db.Model):
    __tablename__ = 'flashcards'
    id = db.Column(db.Integer, primary_key=True)
    lesson_id = db.Column(db.Integer, db.ForeignKey('lessons.id'), nullable=False)
    question = db.Column(db.Text, nullable=False)
    answer = db.Column(db.Text, nullable=False)

class Certificate(db.Model):
    __tablename__ = 'certificates'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    learning_path_id = db.Column(db.Integer, db.ForeignKey('learning_paths.id', ondelete='CASCADE'), nullable=False)
    certificate_code = db.Column(db.String(100), unique=True, nullable=False)
    issue_date = db.Column(db.DateTime, default=datetime.utcnow)
    score_percentage = db.Column(db.Float, default=100.0)

    user = db.relationship('User', backref=db.backref('certificates', lazy=True, cascade="all, delete-orphan"))
    learning_path = db.relationship('LearningPath', backref=db.backref('certificates', lazy=True))

class SystemSetting(db.Model):
    __tablename__ = 'system_settings'
    key = db.Column(db.String(100), primary_key=True)
    value = db.Column(db.Text, nullable=False)
    description = db.Column(db.String(255))

    @classmethod
    def get_setting(cls, key, default=None):
        setting = cls.query.get(key)
        return setting.value if setting else default

    @classmethod
    def set_setting(cls, key, value, description=""):
        setting = cls.query.get(key)
        if setting:
            setting.value = str(value)
        else:
            setting = cls(key=key, value=str(value), description=description)
            db.session.add(setting)
        db.session.commit()

class UserLessonProgress(db.Model):
    __tablename__ = 'user_lesson_progress'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    lesson_id = db.Column(db.Integer, db.ForeignKey('lessons.id', ondelete='CASCADE'), nullable=False)
    video_watched_pct = db.Column(db.Float, default=0.0)
    pdf_read_pct = db.Column(db.Float, default=0.0)
    is_completed = db.Column(db.Boolean, default=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow)

    user = db.relationship('User', backref=db.backref('lesson_progresses', lazy=True, cascade="all, delete-orphan"))
    lesson = db.relationship('Lesson', backref=db.backref('user_progresses', lazy=True, cascade="all, delete-orphan"))

class UserNotification(db.Model):
    __tablename__ = 'user_notifications'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    title = db.Column(db.String(255), nullable=False)
    message = db.Column(db.Text, nullable=False)
    notification_type = db.Column(db.String(50), default='general')
    is_read = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    user = db.relationship('User', backref=db.backref('notifications', lazy=True, cascade="all, delete-orphan"))

class EmailLog(db.Model):
    __tablename__ = 'email_logs'
    id = db.Column(db.Integer, primary_key=True)
    to_email = db.Column(db.String(120), nullable=False)
    subject = db.Column(db.String(255), nullable=False)
    email_type = db.Column(db.String(50), nullable=False)
    status = db.Column(db.String(20), default='PENDING') # 'PENDING', 'SENDING', 'SENT', 'FAILED'
    error_message = db.Column(db.Text, nullable=True)
    retry_count = db.Column(db.Integer, default=0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    sent_at = db.Column(db.DateTime, default=datetime.utcnow)

    @property
    def recipient(self):
        return self.to_email

class ExamViolation(db.Model):
    __tablename__ = 'exam_violations'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    exam_id = db.Column(db.Integer, db.ForeignKey('exams.id', ondelete='CASCADE'), nullable=False)
    violation_type = db.Column(db.String(100), nullable=False) # 'FULLSCREEN_EXIT', 'TAB_SWITCH', 'FOCUS_LOSS', 'COPY_ATTEMPT', 'PASTE_ATTEMPT'
    attempt_number = db.Column(db.Integer, default=1)
    action_taken = db.Column(db.String(100), default='WARNING') # 'WARNING', 'AUTO_SUBMIT'
    details = db.Column(db.Text, nullable=True)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)

    user = db.relationship('User', backref=db.backref('exam_violations', lazy=True, cascade="all, delete-orphan"))
    exam = db.relationship('Exam', backref=db.backref('violations', lazy=True, cascade="all, delete-orphan"))
