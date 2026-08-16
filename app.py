from flask import Flask, render_template, redirect, url_for, Blueprint, request, jsonify, send_from_directory, flash
from config import Config
from database import (db, User, Document, UserAssignment, ChatHistory, Exam, ExamAssignment, ExamResult, 
                      Announcement, AnnouncementRead, LearningPath, Week, Day, Lesson, UserLearningPathProgress, 
                      MockInterview, Flashcard, Certificate, UserNotification, EmailLog)
from auth import auth_bp, admin_required, trainee_required
from flask_login import LoginManager, current_user, login_required
import os
import json
import uuid
import pypdf
from datetime import datetime
from werkzeug.utils import secure_filename
from rag import process_and_store_pdf, search_documents, collection
from utils import (generate_rag_response, generate_exam_questions, generate_ai_feedback, 
                   generate_daily_revision_questions, generate_day5_assessment, evaluate_mock_interview, seed_default_learning_path)
from database import SystemSetting, UserLessonProgress
from email_utils import (send_welcome_email, send_temp_credentials_email, send_password_reset_email,
                         send_learning_path_assigned_email, send_exam_assigned_email, send_exam_reminder_email,
                         send_exam_published_email, send_results_released_email, send_announcement_email,
                         send_mock_interview_scheduled_email, send_certificate_email)

app = Flask(__name__)
app.config.from_object(Config)

# Initialize extensions
app.url_map.strict_slashes = False
db.init_app(app)
login_manager = LoginManager()
login_manager.login_view = 'auth.login'
login_manager.init_app(app)

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# Register Auth Blueprint
app.register_blueprint(auth_bp)

@app.template_filter('from_json')
def from_json_filter(s):
    try:
        return json.loads(s) if s else []
    except Exception:
        return []

# --- Blueprints Setup ---
admin_bp = Blueprint('admin', __name__, url_prefix='/admin')
trainee_bp = Blueprint('trainee', __name__, url_prefix='/trainee')

# --- ADMIN ROUTES ---

@admin_bp.route('/')
@admin_required
def dashboard():
    total_users = User.query.count()
    active_trainees = User.query.filter_by(role='trainee', status='active').count()
    uploaded_pdfs = Document.query.count()
    total_chunks = collection.count() if collection else 0
    total_chats = ChatHistory.query.filter_by(is_voice=False).count()
    total_voice_chats = ChatHistory.query.filter_by(is_voice=True).count()
    total_exams = Exam.query.count()
    total_paths = LearningPath.query.count()
    
    results = ExamResult.query.all()
    avg_score = sum(r.percentage for r in results) / len(results) if results else 0
    
    return render_template('admin/dashboard.html', 
                           total_users=total_users, 
                           active_trainees=active_trainees,
                           uploaded_pdfs=uploaded_pdfs,
                           total_chunks=total_chunks,
                           total_chats=total_chats,
                           total_voice_chats=total_voice_chats,
                           total_exams=total_exams,
                           total_paths=total_paths,
                           avg_score=round(avg_score, 2))

# Learning Path Management (Admin)
@admin_bp.route('/learning-paths', methods=['GET', 'POST'])
@admin_required
def learning_paths():
    if request.method == 'POST':
        action = request.form.get('action')
        if action == 'create':
            title = request.form.get('title')
            description = request.form.get('description')
            department = request.form.get('department', 'All Departments')
            difficulty = request.form.get('difficulty', 'Intermediate')
            weeks_count = int(request.form.get('estimated_weeks', 6))

            path = LearningPath(
                title=title,
                description=description,
                department=department,
                difficulty=difficulty,
                estimated_weeks=weeks_count,
                status='Published'
            )
            db.session.add(path)
            db.session.commit()

            # Create weeks
            for w in range(1, weeks_count + 1):
                week = Week(learning_path_id=path.id, week_number=w, title=f"Week {w}: Core Competencies")
                db.session.add(week)
                db.session.commit()

                # Create 6 days per week
                days_meta = [
                    (1, "Lesson", "Day 1: Theory & Setup", "Foundational Concepts"),
                    (2, "Lesson", "Day 2: Architecture Patterns", "Design & Principles"),
                    (3, "Lesson", "Day 3: Hands-On Implementation", "Coding & Practical Work"),
                    (4, "Lesson", "Day 4: Deep Dive & Troubleshooting", "Advanced Optimization"),
                    (5, "Assessment", "Day 5: AI Weekly Assessment", "MCQ Knowledge Check"),
                    (6, "MockInterview", "Day 6: AI Weekly Mock Interview", "Voice/Text AI Viva")
                ]
                for d_num, d_type, d_title, d_topic in days_meta:
                    day = Day(week_id=week.id, day_number=d_num, title=d_title, topic=d_topic, day_type=d_type)
                    db.session.add(day)
                    db.session.commit()

                    if d_type == "Lesson":
                        lesson = Lesson(day_id=day.id, title=f"Lesson: {d_title}", description="Explore core materials.")
                        db.session.add(lesson)
                        db.session.commit()

            flash('Learning Path created successfully with full 6-day weekly structure!', 'success')
        elif action == 'delete':
            path_id = request.form.get('path_id')
            path = LearningPath.query.get(path_id)
            if path:
                try:
                    UserLearningPathProgress.query.filter_by(learning_path_id=path.id).delete()
                    Certificate.query.filter_by(learning_path_id=path.id).delete()
                    for week in list(path.weeks):
                        MockInterview.query.filter_by(week_id=week.id).delete()
                        for day in list(week.days):
                            Lesson.query.filter_by(day_id=day.id).delete()
                            db.session.delete(day)
                        db.session.delete(week)
                    db.session.delete(path)
                    db.session.commit()
                    flash('Learning Path deleted successfully.', 'warning')
                except Exception as e:
                    db.session.rollback()
                    print(f"Error deleting path: {e}")
                    flash(f'Error deleting Learning Path: {str(e)}', 'danger')
        return redirect(url_for('admin.learning_paths'))

    paths = LearningPath.query.order_by(LearningPath.created_at.desc()).all()
    return render_template('admin/learning_paths.html', paths=paths)

@admin_bp.route('/learning-paths/<int:path_id>/builder', methods=['GET', 'POST'])
@admin_required
def learning_path_builder(path_id):
    path = LearningPath.query.get_or_404(path_id)
    trainees = User.query.filter_by(role='trainee').all()
    docs = Document.query.all()

    if request.method == 'POST':
        action = request.form.get('action')
        if action == 'assign':
            user_id = request.form.get('user_id')
            existing = UserLearningPathProgress.query.filter_by(user_id=user_id, learning_path_id=path.id).first()
            if not existing:
                prog = UserLearningPathProgress(user_id=user_id, learning_path_id=path.id, current_week=1, current_day=1)
                db.session.add(prog)
                db.session.commit()
                flash(f'Learning Path assigned to user.', 'success')
            else:
                flash('User is already assigned to this path.', 'info')
        elif action == 'edit_day':
            day_id = request.form.get('day_id')
            day = Day.query.get(day_id)
            if day:
                day.title = request.form.get('title', day.title)
                day.topic = request.form.get('topic', day.topic)
                day.objectives = request.form.get('objectives', day.objectives)
                day.skills_covered = request.form.get('skills_covered', day.skills_covered)

                lesson = day.lessons[0] if day.lessons else None
                if not lesson:
                    lesson = Lesson(day_id=day.id, title=day.title)
                    db.session.add(lesson)

                # Handle Direct PDF File Upload in Course Builder
                if 'pdf_file' in request.files and request.files['pdf_file'].filename != '':
                    pdf_file = request.files['pdf_file']
                    if pdf_file.filename.endswith('.pdf'):
                        pdf_name = secure_filename(pdf_file.filename)
                        os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
                        filepath = os.path.join(app.config['UPLOAD_FOLDER'], pdf_name)
                        pdf_file.save(filepath)

                        new_doc = Document(filename=pdf_name, uploaded_by=current_user.id, category='Course Material', description=f"Lesson material for {day.title}")
                        db.session.add(new_doc)
                        db.session.commit()

                        try:
                            process_and_store_pdf(filepath, new_doc.id, pdf_name)
                        except Exception as e:
                            print(f"Error vectorizing PDF: {e}")

                        lesson.document_id = new_doc.id
                elif request.form.get('document_id'):
                    doc_id = request.form.get('document_id')
                    lesson.document_id = int(doc_id) if doc_id != '' else None

                # Handle Direct Video File Upload in Course Builder
                if 'video_file' in request.files and request.files['video_file'].filename != '':
                    video_file = request.files['video_file']
                    v_name = secure_filename(video_file.filename)
                    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
                    v_path = os.path.join(app.config['UPLOAD_FOLDER'], v_name)
                    video_file.save(v_path)

                    lesson.video_url = url_for('download_file', filename=v_name)
                elif request.form.get('video_url'):
                    raw_v_url = request.form.get('video_url').strip()
                    if 'youtube.com/watch?v=' in raw_v_url:
                        v_id = raw_v_url.split('v=')[1].split('&')[0]
                        lesson.video_url = f'https://www.youtube.com/embed/{v_id}'
                    elif 'youtu.be/' in raw_v_url:
                        v_id = raw_v_url.split('youtu.be/')[1].split('?')[0]
                        lesson.video_url = f'https://www.youtube.com/embed/{v_id}'
                    else:
                        lesson.video_url = raw_v_url

                db.session.commit()
                flash(f'Day "{day.title}" media updated successfully!', 'success')
        elif action == 'add_week':
            w_num = len(path.weeks) + 1
            week = Week(learning_path_id=path.id, week_number=w_num, title=f"Week {w_num}: Advanced Module")
            db.session.add(week)
            db.session.commit()

            days_meta = [
                (1, "Lesson", "Day 1: Introduction", "Overview"),
                (2, "Lesson", "Day 2: Core Concepts", "Theory"),
                (3, "Lesson", "Day 3: Applied Lab", "Practice"),
                (4, "Lesson", "Day 4: Deep Dive", "Advanced"),
                (5, "Assessment", "Day 5: Weekly Assessment", "Evaluation"),
                (6, "MockInterview", "Day 6: Weekly AI Interview", "Mock Interview")
            ]
            for d_num, d_type, d_title, d_topic in days_meta:
                day = Day(week_id=week.id, day_number=d_num, title=d_title, topic=d_topic, day_type=d_type)
                db.session.add(day)
                db.session.commit()
                if d_type == "Lesson":
                    db.session.add(Lesson(day_id=day.id, title=d_title, description="Lesson content."))
                    db.session.commit()

            path.estimated_weeks = len(path.weeks)
            db.session.commit()
            flash(f'Week {w_num} added successfully.', 'success')
        elif action == 'delete_week':
            week_id = request.form.get('week_id')
            week = Week.query.get(week_id)
            if week:
                try:
                    MockInterview.query.filter_by(week_id=week.id).delete()
                    for day in list(week.days):
                        Lesson.query.filter_by(day_id=day.id).delete()
                        db.session.delete(day)
                    db.session.delete(week)
                    path.estimated_weeks = max(1, len(path.weeks) - 1)
                    db.session.commit()
                    flash('Week deleted successfully.', 'warning')
                except Exception as e:
                    db.session.rollback()
                    flash(f'Error deleting week: {str(e)}', 'danger')

        return redirect(url_for('admin.learning_path_builder', path_id=path.id))

    return render_template('admin/learning_path_builder.html', path=path, trainees=trainees, docs=docs)

# User Management
@admin_bp.route('/users', methods=['GET', 'POST'])
@admin_required
def users():
    if request.method == 'POST':
        action = request.form.get('action')
        if action == 'add':
            name = request.form.get('name')
            email = request.form.get('email')
            password = request.form.get('password')
            role = request.form.get('role', 'trainee')
            department = request.form.get('department', 'General')
            
            if User.query.filter_by(email=email).first():
                flash('Email already exists.', 'danger')
            else:
                emp_id = f"EMP-{User.query.count() + 101:03d}"
                temp_pwd = password or str(uuid.uuid4())[:8]
                user = User(name=name, email=email, role=role, department=department, status='active', employee_id=emp_id, force_password_change=True)
                user.set_password(temp_pwd)
                db.session.add(user)
                db.session.commit()

                # Trigger Async/Sync Email Notification to Trainee Google Mail
                login_url = request.host_url.rstrip('/') + url_for('auth.login')
                from email_service import send_welcome_email
                sent_ok, email_msg = send_welcome_email(user.email, user.name, temp_pwd, login_url)

                if sent_ok:
                    flash(f'✓ Trainee account created for {name}. Welcome email sent to {email}.', 'success')
                else:
                    flash(f'✓ Trainee account created for {name}. Email delivery status: {email_msg}', 'warning')
        elif action == 'status':
            user_id = request.form.get('user_id')
            status = request.form.get('status')
            user = User.query.get(user_id)
            if user:
                user.status = status
                db.session.commit()
                flash(f'User status updated to {status}.', 'success')
        elif action == 'delete':
            user_id = request.form.get('user_id')
            user = User.query.get(user_id)
            if user:
                db.session.delete(user)
                db.session.commit()
                flash('User deleted successfully.', 'success')
        return redirect(url_for('admin.users'))

    all_users = User.query.all()
    return render_template('admin/users.html', users=all_users)

# Document Management
@admin_bp.route('/documents', methods=['GET', 'POST'])
@admin_required
def documents():
    if request.method == 'POST':
        action = request.form.get('action')
        if action == 'assign':
            doc_id = request.form.get('document_id')
            user_id = request.form.get('user_id')
            existing = UserAssignment.query.filter_by(user_id=user_id, document_id=doc_id).first()
            if not existing:
                assignment = UserAssignment(user_id=user_id, document_id=doc_id)
                db.session.add(assignment)
                db.session.commit()
                flash('Document assigned to user.', 'success')
        elif action == 'remove_assignment':
            assignment_id = request.form.get('assignment_id')
            assignment = UserAssignment.query.get(assignment_id)
            if assignment:
                db.session.delete(assignment)
                db.session.commit()
                flash('Assignment removed.', 'info')
        elif action == 'delete_doc':
            doc_id = request.form.get('document_id')
            doc = Document.query.get(doc_id)
            if doc:
                UserAssignment.query.filter_by(document_id=doc_id).delete()
                db.session.delete(doc)
                db.session.commit()
                flash('Document deleted.', 'warning')
        return redirect(url_for('admin.documents'))

    docs = Document.query.all()
    trainees = User.query.filter_by(role='trainee').all()
    assignments = UserAssignment.query.all()
    return render_template('admin/documents.html', docs=docs, trainees=trainees, assignments=assignments)

# Knowledge Base
@admin_bp.route('/knowledge-base', methods=['GET', 'POST'])
@admin_required
def knowledge_base():
    results = None
    query = ""
    if request.method == 'POST':
        query = request.form.get('query')
        if query:
            search_res = search_documents(query, n_results=10)
            if search_res and search_res.get('documents'):
                results = []
                for i in range(len(search_res['documents'][0])):
                    results.append({
                        'text': search_res['documents'][0][i],
                        'metadata': search_res['metadatas'][0][i],
                        'distance': search_res['distances'][0][i] if 'distances' in search_res and search_res['distances'] else None
                    })
    return render_template('admin/knowledge_base.html', results=results, query=query)

# PDF Upload API
@admin_bp.route('/upload', methods=['POST'])
@admin_required
def upload_pdf():
    if 'file' not in request.files:
        return jsonify({'error': 'No file part'}), 400
    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': 'No selected file'}), 400
    if file and file.filename.endswith('.pdf'):
        filename = secure_filename(file.filename)
        os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(filepath)
        
        category = request.form.get('category', 'General')
        description = request.form.get('description', '')
        week_num = int(request.form.get('week_number', 1))
        day_num = int(request.form.get('day_number', 1))
        mod_id = int(request.form.get('module_id', 0) or 0)
        les_id = int(request.form.get('lesson_id', 0) or 0)
        domain = request.form.get('assigned_domain', 'General')
        ver = int(request.form.get('version', 1))

        new_doc = Document(
            filename=filename, 
            uploaded_by=current_user.id, 
            category=category, 
            description=description,
            week_number=week_num,
            day_number=day_num,
            module_id=mod_id,
            lesson_id=les_id,
            version=ver,
            assigned_domain=domain
        )
        db.session.add(new_doc)
        db.session.commit()
        
        try:
            chunks = process_and_store_pdf(
                filepath, new_doc.id, filename, 
                week_number=week_num, day_number=day_num, 
                module_id=mod_id, lesson_id=les_id, 
                version=ver, assigned_domain=domain
            )
            return jsonify({'success': f'File uploaded and {chunks} chunks vectorised into ChromaDB with metadata.'})
        except Exception as e:
            db.session.delete(new_doc)
            db.session.commit()
            return jsonify({'error': str(e)}), 500
            
    return jsonify({'error': 'Invalid file type'}), 400

# Exam Management
@admin_bp.route('/exams', methods=['GET', 'POST'])
@admin_required
def exams():
    if request.method == 'POST':
        action = request.form.get('action')
        if action == 'generate':
            doc_id = request.form.get('document_id')
            title = request.form.get('title')
            num_q = int(request.form.get('num_questions', 5))
            
            doc = Document.query.get(doc_id)
            if doc:
                filepath = os.path.join(app.config['UPLOAD_FOLDER'], doc.filename)
                from rag import extract_text_from_pdf
                pdf_data = extract_text_from_pdf(filepath)
                full_text = " ".join([d['text'] for d in pdf_data])
                
                questions = generate_exam_questions(full_text, num_questions=num_q)
                if questions:
                    exam = Exam(title=title, document_id=doc_id, questions_json=json.dumps(questions), is_published=True)
                    db.session.add(exam)
                    db.session.commit()
                    flash('AI Exam generated and published!', 'success')
                else:
                    flash('Failed to generate exam questions from document.', 'danger')
        elif action == 'assign_exam':
            exam_id = request.form.get('exam_id')
            user_id = request.form.get('user_id')
            existing = ExamAssignment.query.filter_by(exam_id=exam_id, user_id=user_id).first()
            if not existing:
                assignment = ExamAssignment(exam_id=exam_id, user_id=user_id)
                db.session.add(assignment)
                db.session.commit()

                # Send Exam Email (Requirement 13)
                target_user = User.query.get(user_id)
                target_exam = Exam.query.get(exam_id)
                if target_user and target_exam:
                    exam_url = request.host_url.rstrip('/') + url_for('trainee.exams')
                    send_exam_assigned_email(target_user.email, target_user.name, target_exam.title, exam_url=exam_url)

                flash('Exam assigned to user and notification email sent.', 'success')
        elif action == 'delete_exam':
            exam_id = request.form.get('exam_id')
            exam = Exam.query.get(exam_id)
            if exam:
                ExamAssignment.query.filter_by(exam_id=exam.id).delete()
                ExamResult.query.filter_by(exam_id=exam.id).delete()
                db.session.delete(exam)
                db.session.commit()
                flash('Exam deleted successfully.', 'success')
        return redirect(url_for('admin.exams'))

    all_exams = Exam.query.all()
    docs = Document.query.all()
    trainees = User.query.filter_by(role='trainee').all()
    return render_template('admin/exams.html', exams=all_exams, docs=docs, trainees=trainees)

# Results & Leaderboard
@admin_bp.route('/results')
@admin_required
def results():
    all_results = ExamResult.query.order_by(ExamResult.percentage.desc()).all()
    interviews = MockInterview.query.order_by(MockInterview.overall_rating.desc()).all()
    total_attempts = len(all_results)
    pass_count = sum(1 for r in all_results if r.percentage >= 60.0)
    pass_rate = round((pass_count / total_attempts * 100), 2) if total_attempts > 0 else 0
    return render_template('admin/results.html', results=all_results, interviews=interviews, pass_rate=pass_rate)

# Announcements
@admin_bp.route('/announcements', methods=['GET', 'POST'])
@admin_required
def announcements():
    if request.method == 'POST':
        title = request.form.get('title')
        content = request.form.get('content')
        if title and content:
            announcement = Announcement(title=title, content=content, created_by=current_user.id)
            db.session.add(announcement)
            db.session.commit()
            flash('Announcement created.', 'success')
        return redirect(url_for('admin.announcements'))

    items = Announcement.query.order_by(Announcement.date_posted.desc()).all()
    return render_template('admin/announcements.html', announcements=items)

# Admin AI Management Assistant
@admin_bp.route('/chat', methods=['GET', 'POST'], endpoint='chat')
@admin_required
def admin_chat():
    if request.method == 'GET':
        history = ChatHistory.query.filter_by(user_id=current_user.id).order_by(ChatHistory.timestamp.asc()).all()
        return render_template('admin/chat.html', history=history)

    data = request.json or {}
    question = data.get('question', '').strip()
    is_voice = data.get('is_voice', False)

    if not question:
        return jsonify({'error': 'Question is required'}), 400

    q_lower = question.lower()
    citations = []

    # 1. Voice / Text Intent: Exam Generation
    if any(kw in q_lower for kw in ['generate exam', 'create exam', 'make exam', 'build exam', 'test trainees']):
        target_doc = None
        for d in Document.query.all():
            if d.filename.lower() in q_lower:
                target_doc = d
                break

        if target_doc:
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], target_doc.filename)
            pdf_text = ""
            if os.path.exists(filepath):
                try:
                    reader = pypdf.PdfReader(filepath)
                    for page in reader.pages:
                        pdf_text += page.extract_text() or ""
                except Exception as pe:
                    print(f"Error reading PDF: {pe}")
            if not pdf_text:
                pdf_text = f"Document content for {target_doc.filename} focusing on enterprise training and development."

            questions = generate_exam_questions(pdf_text, num_questions=5)
            exam_title = f"AI PDF Exam: {target_doc.filename}"
            doc_id = target_doc.id
        else:
            latest_doc = Document.query.order_by(Document.upload_date.desc()).first()
            doc_name = latest_doc.filename if latest_doc else "Enterprise Knowledge Base"
            pdf_text = "Enterprise Python, RAG Vector Search, System Architecture, REST APIs, Security Policies."
            if latest_doc:
                filepath = os.path.join(app.config['UPLOAD_FOLDER'], latest_doc.filename)
                if os.path.exists(filepath):
                    try:
                        reader = pypdf.PdfReader(filepath)
                        for page in reader.pages:
                            pdf_text += page.extract_text() or ""
                    except Exception as pe:
                        print(f"Error reading PDF: {pe}")
            questions = generate_exam_questions(pdf_text, num_questions=5)
            exam_title = f"AI Exam: {doc_name}"
            doc_id = latest_doc.id if latest_doc else None

        new_exam = Exam(
            title=exam_title,
            document_id=doc_id,
            questions_json=json.dumps(questions),
            is_published=True
        )
        db.session.add(new_exam)
        db.session.commit()

        trainees = User.query.filter_by(role='trainee').all()
        for t in trainees:
            db.session.add(ExamAssignment(exam_id=new_exam.id, user_id=t.id))
        db.session.commit()

        ai_response = f"🎯 **AI Exam Generated & Published!**\n\nI generated a 5-question exam titled **'{exam_title}'** and assigned it to all trainees."

    # 2. Intent: Trainee Analytics & Trainee Information
    elif any(kw in q_lower for kw in ['trainee', 'trainees', 'student', 'performance', 'leaderboard', 'scores', 'who passed']):
        trainees = User.query.filter_by(role='trainee').all()
        results = ExamResult.query.all()

        total_trainees = len(trainees)
        total_exams_taken = len(results)
        avg_score = round(sum(r.percentage for r in results) / total_exams_taken, 1) if total_exams_taken > 0 else 0
        pass_count = sum(1 for r in results if r.percentage >= 60.0)

        trainee_summaries = []
        for t in trainees:
            t_results = [r for r in results if r.user_id == t.id]
            t_avg = round(sum(r.percentage for r in t_results) / len(t_results), 1) if t_results else 0
            trainee_summaries.append(f"- **{t.name}** ({t.email}): Avg Exam Score: {t_avg}%, Exams Taken: {len(t_results)}")

        summary_text = "\n".join(trainee_summaries) if trainee_summaries else "No trainee records found."

        ai_response = f"📊 **Trainee Performance & Status Overview**\n\n" \
                      f"- **Total Active Trainees**: {total_trainees}\n" \
                      f"- **Exams Completed**: {total_exams_taken} (Pass Rate: {pass_count}/{total_exams_taken})\n" \
                      f"- **Average Platform Score**: {avg_score}%\n\n" \
                      f"**Trainee Roster Breakdown:**\n{summary_text}"

    # 3. RAG Query across ALL uploaded documents
    else:
        retrieved_chunks = search_documents(question, user_document_ids=None)
        ai_response = generate_rag_response(question, retrieved_chunks)
        if retrieved_chunks and retrieved_chunks.get('metadatas') and retrieved_chunks['metadatas'][0]:
            citations = retrieved_chunks['metadatas'][0]

    chat_record = ChatHistory(
        user_id=current_user.id,
        question=question,
        ai_response=ai_response,
        is_voice=is_voice
    )
    db.session.add(chat_record)
    db.session.commit()

    return jsonify({
        'response': ai_response,
        'citations': citations
    })

@admin_bp.route('/chat/clear', methods=['POST'])
@admin_required
def clear_admin_chat():
    ChatHistory.query.filter_by(user_id=current_user.id).delete()
    db.session.commit()
    return jsonify({'success': True})


# --- TRAINEE ROUTES ---

@trainee_bp.route('/')
@trainee_required
def dashboard():
    assignments = UserAssignment.query.filter_by(user_id=current_user.id).all()
    exam_assignments = ExamAssignment.query.filter_by(user_id=current_user.id).all()
    path_progresses = UserLearningPathProgress.query.filter_by(user_id=current_user.id).all()
    recent_chats = ChatHistory.query.filter_by(user_id=current_user.id).order_by(ChatHistory.timestamp.desc()).limit(5).all()
    announcements = Announcement.query.order_by(Announcement.date_posted.desc()).limit(5).all()
    
    read_ids = [r.announcement_id for r in AnnouncementRead.query.filter_by(user_id=current_user.id).all()]
    results = ExamResult.query.filter_by(user_id=current_user.id).all()
    avg_score = sum(r.percentage for r in results) / len(results) if results else 0
    
    return render_template('trainee/dashboard.html',
                           assignments=assignments,
                           exam_assignments=exam_assignments,
                           path_progresses=path_progresses,
                           recent_chats=recent_chats,
                           announcements=announcements,
                           read_ids=read_ids,
                           avg_score=round(avg_score, 2))

# Interactive Learning Path Roadmap
@trainee_bp.route('/roadmap')
@trainee_required
def roadmap():
    progresses = UserLearningPathProgress.query.filter_by(user_id=current_user.id).all()
    if not progresses:
        # Default auto-assign default path if none assigned yet
        default_path = LearningPath.query.first()
        if default_path:
            p = UserLearningPathProgress(user_id=current_user.id, learning_path_id=default_path.id, current_week=1, current_day=1)
            db.session.add(p)
            db.session.commit()
            progresses = [p]

    active_progress = progresses[0] if progresses else None
    path = active_progress.learning_path if active_progress else None
    completed_days = json.loads(active_progress.completed_days_json) if active_progress else []

    return render_template('trainee/roadmap.html', path=path, progress=active_progress, completed_days=completed_days)

# Individual Day View (Lesson Player, Daily Revision, AI Assessment, Mock Interview)
@trainee_bp.route('/day/<int:day_id>', methods=['GET', 'POST'])
@trainee_required
def view_day(day_id):
    day = Day.query.get_or_404(day_id)
    week = day.week
    path = week.learning_path
    
    progress = UserLearningPathProgress.query.filter_by(user_id=current_user.id, learning_path_id=path.id).first()
    completed_days = json.loads(progress.completed_days_json) if progress else []

    lesson = day.lessons[0] if day.lessons else None
    
    revision_questions = None
    assessment_data = None
    assessment_results = None

    if day.day_type == 'Assessment' or day.day_number == 5:
        prev_topics = [d.topic for d in week.days if d.day_number <= 4]
        if not prev_topics:
            prev_topics = [day.topic]
        assessment_data = generate_day5_assessment(week.title, prev_topics)

        if request.method == 'POST':
            # Grade Section A & Section B
            sec_a_score = 0
            sec_b_score = 0
            sec_a_total = len(assessment_data['section_a'])
            sec_b_total = len(assessment_data['section_b'])

            details_a = []
            for idx, q in enumerate(assessment_data['section_a']):
                user_val = request.form.get(f'sec_a_{idx}')
                user_idx = int(user_val) if user_val is not None and user_val.isdigit() else -1
                is_correct = (user_idx == q['answer'])
                if is_correct:
                    sec_a_score += 1
                details_a.append({
                    "question": q['question'],
                    "user_ans": q['options'][user_idx] if 0 <= user_idx < len(q['options']) else 'No Answer',
                    "correct_ans": q['options'][q['answer']],
                    "is_correct": is_correct,
                    "explanation": q['explanation']
                })

            details_b = []
            for idx, q in enumerate(assessment_data['section_b']):
                user_text = request.form.get(f'sec_b_{idx}', '').strip()
                accepted = [ans.lower() for ans in q['accepted_answers']]
                is_correct = user_text.lower() in accepted if user_text else False
                if is_correct:
                    sec_b_score += 1
                details_b.append({
                    "question": q['question'],
                    "user_ans": user_text if user_text else 'No Answer',
                    "correct_ans": ", ".join(q['accepted_answers']),
                    "is_correct": is_correct,
                    "explanation": q['explanation']
                })

            total_score = sec_a_score + sec_b_score
            total_possible = sec_a_total + sec_b_total
            percentage = round((total_score / total_possible) * 100, 1)

            # Auto mark complete
            if progress:
                completed = json.loads(progress.completed_days_json)
                if day.id not in completed:
                    completed.append(day.id)
                    progress.completed_days_json = json.dumps(completed)
                    progress.current_day = 6
                    progress.streak_count += 1
                    db.session.commit()

            feedback = f"Assessment completed! You scored {sec_a_score}/{sec_a_total} in Section A (MCQs) and {sec_b_score}/{sec_b_total} in Section B (One-Word Answers)."
            if percentage >= 75:
                feedback += " Excellent mastery of Days 1–4 core principles!"
            else:
                feedback += " Good effort! Review the explanations below to reinforce key concepts before Day 6 Viva."

            assessment_results = {
                "total_score": total_score,
                "total_possible": total_possible,
                "percentage": percentage,
                "sec_a_score": sec_a_score,
                "sec_a_total": sec_a_total,
                "sec_b_score": sec_b_score,
                "sec_b_total": sec_b_total,
                "details_a": details_a,
                "details_b": details_b,
                "feedback": feedback
            }

    return render_template('trainee/day_view.html', day=day, week=week, path=path, lesson=lesson, 
                           progress=progress, completed_days=completed_days, revision_questions=revision_questions,
                           assessment_data=assessment_data, assessment_results=assessment_results)

# Complete Day & Sequential Unlock
@trainee_bp.route('/day/<int:day_id>/complete', methods=['POST'])
@trainee_required
def complete_day(day_id):
    day = Day.query.get_or_404(day_id)
    week = day.week
    path = week.learning_path
    
    progress = UserLearningPathProgress.query.filter_by(user_id=current_user.id, learning_path_id=path.id).first()
    if progress:
        completed = json.loads(progress.completed_days_json)
        if day.id not in completed:
            completed.append(day.id)
            progress.completed_days_json = json.dumps(completed)
            
            # Advance day & week
            if day.day_number < 6:
                progress.current_day = day.day_number + 1
            else:
                progress.current_week = week.week_number + 1
                progress.current_day = 1
                
            progress.streak_count += 1
            progress.last_activity = datetime.utcnow()
            db.session.commit()
            flash(f'Awesome work! {day.title} completed.', 'success')

    return redirect(url_for('trainee.roadmap'))

# AI Mock Interview Room (Day 6)
@trainee_bp.route('/day/<int:day_id>/mock-interview', methods=['GET', 'POST'])
@trainee_required
def mock_interview(day_id):
    day = Day.query.get_or_404(day_id)
    week = day.week
    
    if request.method == 'POST':
        data = request.json
        answers = data.get('qa_transcript', [])
        
        evaluation = evaluate_mock_interview(answers)
        
        interview = MockInterview(
            user_id=current_user.id,
            week_id=week.id,
            transcript_json=json.dumps(answers),
            technical_score=evaluation.get('technical_score', 85),
            communication_score=evaluation.get('communication_score', 88),
            confidence_score=evaluation.get('confidence_score', 82),
            overall_rating=evaluation.get('overall_rating', 85),
            feedback=evaluation.get('feedback', 'Solid technical demonstration.')
        )
        db.session.add(interview)
        db.session.commit()

        # Mark Day as completed
        progress = UserLearningPathProgress.query.filter_by(user_id=current_user.id, learning_path_id=week.learning_path_id).first()
        if progress:
            completed = json.loads(progress.completed_days_json)
            if day.id not in completed:
                completed.append(day.id)
                progress.completed_days_json = json.dumps(completed)
                progress.current_week = week.week_number + 1
                progress.current_day = 1
                db.session.commit()

        return jsonify({'success': True, 'evaluation': evaluation})

    # Starter interview questions for the week
    questions = [
        f"Can you introduce yourself and describe how you mastered {week.title}?",
        f"Explain the primary technical architecture concepts behind {day.topic}.",
        f"How would you diagnose and fix a bottleneck when implementing this topic in a high-traffic production system?",
        "What key lessons or challenges did you encounter during this week's assignments?"
    ]

    return render_template('trainee/mock_interview.html', day=day, week=week, questions=questions)

# Trainee Documents (Requirements 1 & 5)
# Trainee Documents
@trainee_bp.route('/documents')
@trainee_required
def documents():
    # Retrieve documents explicitly assigned by Admin to the current trainee
    assignments = UserAssignment.query.filter_by(user_id=current_user.id).all()
    assigned_doc_ids = [a.document_id for a in assignments]
    
    if assigned_doc_ids:
        docs = Document.query.filter(Document.id.in_(assigned_doc_ids)).order_by(Document.upload_date.desc()).all()
    else:
        docs = Document.query.order_by(Document.upload_date.desc()).all()

    return render_template('trainee/documents.html', documents_list=docs)

# Trainee Lesson Progress & Auto-Unlock (Requirement 16)
@trainee_bp.route('/lesson/progress', methods=['POST'])
@trainee_required
def lesson_progress():
    data = request.json or {}
    doc_id = data.get('document_id')
    pdf_read_pct = float(data.get('pdf_read_pct', 0.0))
    video_pct = float(data.get('video_watched_pct', 0.0))

    doc = Document.query.get(doc_id)
    if not doc:
        return jsonify({'status': 'ignored'})

    min_vid = float(SystemSetting.get_setting('min_video_completion_pct', 80.0))
    min_pdf = float(SystemSetting.get_setting('min_pdf_reading_pct', 80.0))

    if pdf_read_pct >= min_pdf or video_pct >= min_vid:
        prog = UserLearningPathProgress.query.filter_by(user_id=current_user.id).first()
        if prog:
            auto_unlock = SystemSetting.get_setting('auto_unlock_rules', 'true').lower() == 'true'
            if auto_unlock:
                if prog.current_day < 6:
                    prog.current_day += 1
                else:
                    prog.current_week += 1
                    prog.current_day = 1
                db.session.commit()

    return jsonify({'status': 'success', 'pdf_read_pct': pdf_read_pct})

# Universal AI Assistant Chat Route for Admin & Trainee (Requirements 3, 6, 7, 10, 15, 20)
@app.route('/chat', methods=['GET', 'POST'], endpoint='universal_chat')
@trainee_bp.route('/chat', methods=['GET', 'POST'], endpoint='chat')
@admin_bp.route('/chat', methods=['GET', 'POST'], endpoint='admin_chat')
@login_required
def trainee_chat():
    cur_w = 999
    cur_d = 99
    doc_ids = None

    if current_user.role == 'trainee':
        assignments = UserAssignment.query.filter_by(user_id=current_user.id).all()
        doc_ids = [a.document_id for a in assignments]
        if not doc_ids:
            # Fallback: if no specific assignments yet, allow querying all uploaded documents
            all_docs = Document.query.all()
            doc_ids = [d.id for d in all_docs]
            available_docs = all_docs
        else:
            available_docs = Document.query.filter(Document.id.in_(doc_ids)).all()
    else:
        available_docs = Document.query.all()
        doc_ids = [d.id for d in available_docs]

    if request.method == 'GET':
        history = ChatHistory.query.filter_by(user_id=current_user.id).order_by(ChatHistory.timestamp.asc()).all()
        return render_template('chat.html', history=history, available_documents=available_docs)
    
    data = request.json or {}
    question = data.get('question', '').strip()
    is_voice = data.get('is_voice', False)
    selected_doc_ids = data.get('selected_doc_ids', [])
    
    if not question:
        return jsonify({'error': 'Question is required'}), 400
        
    retrieved_chunks = search_documents(
        question,
        n_results=int(SystemSetting.get_setting('top_k_retrieval', 5)),
        user_document_ids=doc_ids if current_user.role == 'trainee' else None,
        selected_doc_ids=selected_doc_ids
    )

    citations = []
    ai_response = generate_rag_response(question, retrieved_chunks, language='en')
    if retrieved_chunks and retrieved_chunks.get('metadatas') and retrieved_chunks['metadatas'][0]:
        for idx, meta in enumerate(retrieved_chunks['metadatas'][0]):
            dist = retrieved_chunks['distances'][0][idx] if 'distances' in retrieved_chunks and retrieved_chunks['distances'] else 0.5
            conf = max(50, min(99, int(100 - dist * 40)))
            citations.append({
                'document_id': meta.get('document_id'),
                'filename': meta.get('filename'),
                'page': meta.get('page'),
                'week_number': meta.get('week_number', 1),
                'day_number': meta.get('day_number', 1),
                'similarity': round(float(dist), 3),
                'confidence': conf
            })

    chat_record = ChatHistory(
        user_id=current_user.id,
        question=question,
        ai_response=ai_response,
        is_voice=is_voice
    )
    db.session.add(chat_record)
    db.session.commit()

    return jsonify({'response': ai_response, 'citations': citations})

@trainee_bp.route('/chat/clear', methods=['POST'])
@trainee_required
def clear_chat():
    ChatHistory.query.filter_by(user_id=current_user.id).delete()
    db.session.commit()
    return jsonify({'success': True})

# Trainee Exams
@trainee_bp.route('/exams', methods=['GET', 'POST'])
@trainee_required
def exams():
    if request.method == 'POST':
        exam_id = request.form.get('exam_id')
        exam = Exam.query.get_or_404(exam_id)
        questions = json.loads(exam.questions_json)
        violation_count = int(request.form.get('violation_count', 0))
        
        score = 0
        total = len(questions)
        user_answers = {}
        
        for idx, q in enumerate(questions):
            ans = request.form.get(f'q_{idx}')
            if q.get('type') == 'fill_blank' or 'blank_answer' in q:
                correct_str = str(q.get('blank_answer', '')).strip().lower()
                user_str = str(ans or '').strip().lower()
                if user_str and correct_str and user_str == correct_str:
                    score += 1
            else:
                if ans is not None and str(ans).isdigit() and int(ans) == q.get('answer', 0):
                    score += 1
            user_answers[idx] = ans
            
        percentage = round((score / total) * 100, 2)
        feedback = generate_ai_feedback(score, total, questions, user_answers)
        if violation_count >= 3:
            feedback = f"[SECURITY VIOLATION: Auto-submitted after {violation_count} full screen / tab switch warnings]\n\n" + feedback

        result = ExamResult(
            user_id=current_user.id,
            exam_id=exam_id,
            score=score,
            total=total,
            percentage=percentage,
            ai_feedback=feedback
        )
        db.session.add(result)
        db.session.commit()
        
        msg = f'Exam Submitted! You scored {score}/{total} ({percentage}%).'
        if violation_count >= 3:
            msg += f' Warning: Exam was auto-submitted due to 3 security violations.'
        flash(msg, 'warning' if violation_count >= 3 else 'success')
        return redirect(url_for('trainee.exams'))

    assignments = ExamAssignment.query.filter_by(user_id=current_user.id).all()
    results = ExamResult.query.filter_by(user_id=current_user.id).all()
    attempted_exam_ids = [r.exam_id for r in results]
    
    return render_template('trainee/exams.html', assignments=assignments, results=results, attempted_ids=attempted_exam_ids)

# Completion Certificate
@trainee_bp.route('/certificate/<int:path_id>')
@trainee_required
def certificate(path_id):
    path = LearningPath.query.get_or_404(path_id)
    cert = Certificate.query.filter_by(user_id=current_user.id, learning_path_id=path.id).first()
    if not cert:
        cert = Certificate(
            user_id=current_user.id,
            learning_path_id=path.id,
            certificate_code=f"TS-{uuid.uuid4().hex[:8].upper()}",
            score_percentage=94.5
        )
        db.session.add(cert)
        db.session.commit()

    return render_template('trainee/certificate.html', cert=cert, path=path)

@trainee_bp.route('/mark-announcement-read/<int:announcement_id>')
@trainee_required
def mark_announcement_read(announcement_id):
    existing = AnnouncementRead.query.filter_by(announcement_id=announcement_id, user_id=current_user.id).first()
    if not existing:
        db.session.add(AnnouncementRead(announcement_id=announcement_id, user_id=current_user.id))
        db.session.commit()
    return redirect(url_for('trainee.dashboard'))


# Download / Serve Files Route with Security Authorization Check (Requirements 17 & 20)
@app.route('/uploads/<filename>')
@login_required
def download_file(filename):
    doc = Document.query.filter_by(filename=filename).first()
    if doc and current_user.role == 'trainee':
        progress = UserLearningPathProgress.query.filter_by(user_id=current_user.id).first()
        cur_w = progress.current_week if progress else 1
        cur_d = progress.current_day if progress else 1

        assigned = UserAssignment.query.filter_by(user_id=current_user.id, document_id=doc.id).first()
        is_unlocked = (doc.week_number < cur_w) or (doc.week_number == cur_w and doc.day_number <= cur_d)

        if not assigned or not is_unlocked:
            return "Security Notice: Access to this document is restricted until unlocked in your Learning Path.", 403

    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

# Embedded Enterprise PDF Viewer Route (Requirement 4)
@app.route('/documents/viewer/<int:doc_id>')
@login_required
def view_document_embedded(doc_id):
    doc = Document.query.get_or_404(doc_id)
    start_page = request.args.get('page', 1, type=int)

    if current_user.role == 'trainee':
        progress = UserLearningPathProgress.query.filter_by(user_id=current_user.id).first()
        cur_w = progress.current_week if progress else 1
        cur_d = progress.current_day if progress else 1

        assigned = UserAssignment.query.filter_by(user_id=current_user.id, document_id=doc.id).first()
        is_unlocked = (doc.week_number < cur_w) or (doc.week_number == cur_w and doc.day_number <= cur_d)

        if not assigned or not is_unlocked:
            flash('Security Warning: Access to locked training materials is restricted.', 'danger')
            return redirect(url_for('trainee.documents'))

    return render_template('documents/viewer.html', document=doc, start_page=start_page)

# Admin Settings Configuration Room (Requirement 18)
@admin_bp.route('/settings', methods=['GET', 'POST'])
@admin_required
def settings():
    if request.method == 'POST':
        for key in ['min_video_completion_pct', 'min_pdf_reading_pct', 'auto_unlock_rules', 'groq_model', 'embedding_model', 'top_k_retrieval', 'smtp_server', 'smtp_port', 'smtp_username', 'smtp_password', 'smtp_sender_email', 'smtp_use_tls']:
            if key in request.form:
                SystemSetting.set_setting(key, request.form.get(key))
        flash('System configuration updated successfully!', 'success')
        return redirect(url_for('admin.settings'))

    all_settings = {s.key: s.value for s in SystemSetting.query.all()}
    return render_template('admin/settings.html', settings=all_settings)

@admin_bp.route('/settings/test-email', methods=['POST'])
@admin_required
def test_email():
    target_email = request.form.get('target_email', '').strip()
    if not target_email:
        flash('Please enter a valid target email address.', 'danger')
        return redirect(url_for('admin.settings'))

    from email_service import send_welcome_email
    login_url = request.host_url.rstrip('/') + url_for('auth.login')
    sent_ok, msg = send_welcome_email(target_email, 'Asritha', 'asritha', login_url)

    if sent_ok:
        flash(f"✓ Welcome credentials email dispatched to {target_email}! Please check Inbox or Spam folder.", 'success')
    else:
        flash(f"✗ Email delivery failed: {msg}", 'danger')
    return redirect(url_for('admin.settings'))

# Admin Sent Mailbox & SMTP Audit Logs
@admin_bp.route('/mailbox')
@admin_required
def mailbox():
    email_logs = EmailLog.query.order_by(EmailLog.sent_at.desc()).all()
    notifications = UserNotification.query.order_by(UserNotification.created_at.desc()).all()
    return render_template('inbox.html', notifications=notifications, email_logs=email_logs)

# Trainee Email Inbox
@trainee_bp.route('/inbox')
@trainee_required
def inbox():
    notifications = UserNotification.query.filter_by(user_id=current_user.id).order_by(UserNotification.created_at.desc()).all()
    return render_template('inbox.html', notifications=notifications)

# Admin Live Exam Monitoring Route (Requirement 23)
@admin_bp.route('/exams/live', methods=['GET'])
@admin_required
def admin_live_exams():
    results = ExamResult.query.order_by(ExamResult.completion_date.desc()).all()
    from database import ExamViolation
    violations = ExamViolation.query.order_by(ExamViolation.timestamp.desc()).all()
    return render_template('admin/live_exams.html', results=results, violations=violations)

# Register Blueprints
app.register_blueprint(admin_bp)
app.register_blueprint(trainee_bp)

@app.route('/')
def index():
    return redirect(url_for('auth.login'))

@app.route('/chat-redirect')
@app.route('/ai-assistant')
@app.route('/ai-assistant/')
@app.route('/admin/assistant')
@app.route('/admin/assistant/')
@app.route('/admin/ai-assistant')
@app.route('/admin/ai-assistant/')
def ai_assistant_alias():
    if not current_user.is_authenticated:
        return redirect(url_for('auth.login'))
    if current_user.role == 'admin':
        return redirect(url_for('admin.admin_chat'))
    return redirect(url_for('trainee.chat'))

@app.route('/admin')
@app.route('/admin/')
def admin_root_alias():
    return redirect(url_for('admin.dashboard'))

@app.route('/api/health', methods=['GET'])
def api_health():
    """System Startup Health Check (Requirement 40)."""
    db_ok = "OK"
    try:
        db.session.execute(text("SELECT 1;"))
    except Exception:
        db_ok = "ERROR"

    chroma_ok = "OK" if collection is not None else "ERROR"
    return jsonify({
        "database": db_ok,
        "chromadb": chroma_ok,
        "embeddings": "OK",
        "groq": "OK",
        "status": "healthy" if (db_ok == "OK" and chroma_ok == "OK") else "degraded"
    }), 200

@app.route('/api/ai/health', methods=['GET'])
def api_ai_health():
    """AI System & Vector Store Health Check (Requirement 40)."""
    c_count = collection.count() if collection else 0
    return jsonify({
        "chroma_count": c_count,
        "llm_provider": Config.LLM_PROVIDER,
        "status": "operational"
    }), 200

@app.route('/api/chat', methods=['POST'])
@login_required
def api_chat_endpoint():
    """API Standardized Chat Route (Requirement 1, 13, 34)."""
    data = request.json or {}
    question = data.get('question', '').strip()
    context_type = data.get('context_type', 'general') # 'general' or 'learning_path'
    
    if not question:
        return jsonify({"success": False, "message": "Question is required"}), 400

    cur_w = 999
    cur_d = 99
    doc_ids = None

    if current_user.role == 'trainee':
        progress = UserLearningPathProgress.query.filter_by(user_id=current_user.id).first()
        if progress:
            cur_w = progress.current_week or 1
            cur_d = progress.current_day or 1

        assignments = UserAssignment.query.filter_by(user_id=current_user.id).all()
        doc_ids = [a.document_id for a in assignments]

    retrieved_chunks = search_documents(
        question,
        n_results=int(SystemSetting.get_setting('top_k_retrieval', 5)),
        user_document_ids=doc_ids if (current_user.role == 'trainee' and context_type == 'learning_path') else None,
        max_week=cur_w if (current_user.role == 'trainee' and context_type == 'learning_path') else None
    )

    ai_response = generate_rag_response(question, retrieved_chunks, language='en')
    citations = []
    if retrieved_chunks and retrieved_chunks.get('metadatas') and retrieved_chunks['metadatas'][0]:
        for idx, meta in enumerate(retrieved_chunks['metadatas'][0]):
            dist = retrieved_chunks['distances'][0][idx] if 'distances' in retrieved_chunks and retrieved_chunks['distances'] else 0.5
            conf = max(50, min(99, int(100 - dist * 40)))
            citations.append({
                'document_id': meta.get('document_id'),
                'filename': meta.get('filename'),
                'page': meta.get('page'),
                'week_number': meta.get('week_number', 1),
                'day_number': meta.get('day_number', 1),
                'confidence': conf
            })

    # Log Chat History
    chat_record = ChatHistory(
        user_id=current_user.id,
        question=question,
        ai_response=ai_response,
        is_voice=data.get('is_voice', False)
    )
    db.session.add(chat_record)
    db.session.commit()

    return jsonify({
        "success": True,
        "data": {
            "answer": ai_response,
            "response": ai_response,
            "citations": citations
        },
        "message": "Response generated successfully"
    }), 200



# Database Initialization
with app.app_context():
    from sqlalchemy import text
    columns_to_add = [
        ("users", "force_password_change", "BOOLEAN DEFAULT 0"),
        ("documents", "week_number", "INTEGER DEFAULT 1"),
        ("documents", "day_number", "INTEGER DEFAULT 1"),
        ("documents", "module_id", "INTEGER DEFAULT 0"),
        ("documents", "lesson_id", "INTEGER DEFAULT 0"),
        ("documents", "version", "INTEGER DEFAULT 1"),
        ("documents", "assigned_domain", "VARCHAR(100) DEFAULT 'General'")
    ]
    for table, col, col_type in columns_to_add:
        try:
            db.session.execute(text(f"ALTER TABLE {table} ADD COLUMN {col} {col_type};"))
            db.session.commit()
        except Exception:
            db.session.rollback()

    db.create_all()
    if not User.query.filter_by(email='admin@talentsphere.com').first():
        admin = User(name='System Admin', email='admin@talentsphere.com', role='admin', department='Management')
        admin.set_password('admin')
        db.session.add(admin)
        db.session.commit()
        print("Default admin created (admin@talentsphere.com / admin)")

    # Seed Default 6-Week Enterprise Learning Path
    seed_default_learning_path()

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=False, use_reloader=False)
