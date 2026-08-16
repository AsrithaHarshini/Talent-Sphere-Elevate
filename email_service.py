import os
import smtplib
import socket
import threading
import time
from datetime import datetime
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from flask import render_template
from config import Config
from database import SystemSetting, db, EmailLog

def get_smtp_config():
    """Resolves active SMTP configuration from SystemSetting (if inside app context) or Config."""
    def safe_get_setting(key, default=''):
        try:
            val = SystemSetting.get_setting(key, default)
            return val if val is not None else default
        except Exception:
            return default

    srv_val = safe_get_setting('smtp_server', '') or safe_get_setting('mail_server', '')
    if not srv_val or srv_val.isdigit():
        srv_val = Config.MAIL_SERVER or 'smtp.gmail.com'

    port_val = safe_get_setting('smtp_port', '') or safe_get_setting('mail_port', '')
    try:
        port = int(port_val) if port_val and str(port_val).isdigit() else int(Config.MAIL_PORT or 587)
    except Exception:
        port = 587

    user = safe_get_setting('smtp_username', '') or safe_get_setting('mail_username', '') or Config.MAIL_USERNAME
    password = safe_get_setting('smtp_password', '') or safe_get_setting('mail_password', '') or Config.MAIL_PASSWORD
    sender = safe_get_setting('smtp_sender_email', '') or safe_get_setting('mail_default_sender', '') or Config.MAIL_DEFAULT_SENDER or user
    sender_name = safe_get_setting('mail_default_sender_name', '') or Config.MAIL_DEFAULT_SENDER_NAME or 'Talent Management Platform'
    use_tls = (safe_get_setting('smtp_use_tls', '') or str(Config.MAIL_USE_TLS)).lower() == 'true'
    use_ssl = (safe_get_setting('smtp_use_ssl', '') or str(Config.MAIL_USE_SSL)).lower() == 'true'

    clean_pwd = password.strip().replace(" ", "") if password else ""
    return {
        'server': srv_val,
        'port': port,
        'user': user,
        'password': clean_pwd,
        'sender': sender,
        'sender_name': sender_name,
        'use_tls': use_tls,
        'use_ssl': use_ssl
    }

def test_smtp_connection(to_email=None):
    """
    Executes a 5-step diagnostic handshake with SMTP server:
    1. Environment & Config Validation
    2. Socket & DNS Connection
    3. STARTTLS Security Upgrade
    4. Authentication
    5. Test Email Submission (if to_email is provided)
    Returns a structured diagnostic dict with safe messages (passwords masked).
    """
    cfg = get_smtp_config()
    steps = []
    
    # 1. Config Check
    masked_user = f"{cfg['user'][:2]}*****@{cfg['user'].split('@')[-1]}" if '@' in cfg['user'] else "Unconfigured"
    steps.append({"step": "Configuration Check", "status": "PASS" if cfg['server'] and cfg['user'] and cfg['password'] else "FAIL", "detail": f"Host: {cfg['server']}, Port: {cfg['port']}, User: {masked_user}"})

    if not cfg['server'] or not cfg['user'] or not cfg['password']:
        return {
            "success": False,
            "stage": "Configuration",
            "message": "SMTP credentials incomplete. Please set MAIL_USERNAME and MAIL_PASSWORD in .env or Admin Settings.",
            "steps": steps
        }

    # 2. Connection Test
    server_obj = None
    try:
        if cfg['port'] == 465 or cfg['use_ssl']:
            server_obj = smtplib.SMTP_SSL(cfg['server'], cfg['port'], timeout=12)
        else:
            server_obj = smtplib.SMTP(cfg['server'], cfg['port'], timeout=12)
        steps.append({"step": "SMTP Connection", "status": "PASS", "detail": f"Connected to {cfg['server']}:{cfg['port']}"})
    except socket.gaierror:
        steps.append({"step": "SMTP Connection", "status": "FAIL", "detail": f"Could not resolve host {cfg['server']} (DNS Failure)"})
        return {"success": False, "stage": "DNS/Connection", "message": f"DNS Failure: Cannot resolve SMTP host '{cfg['server']}'. Check network connection.", "steps": steps}
    except (socket.timeout, ConnectionRefusedError, smtplib.SMTPConnectError) as err:
        steps.append({"step": "SMTP Connection", "status": "FAIL", "detail": str(err)})
        return {"success": False, "stage": "Connection", "message": f"Connection refused or timed out connecting to {cfg['server']}:{cfg['port']}.", "steps": steps}
    except Exception as err:
        steps.append({"step": "SMTP Connection", "status": "FAIL", "detail": str(err)})
        return {"success": False, "stage": "Connection", "message": f"Connection failed: {err}", "steps": steps}

    # 3. EHLO & STARTTLS
    try:
        server_obj.ehlo()
        if cfg['use_tls'] and cfg['port'] != 465:
            server_obj.starttls()
            server_obj.ehlo()
            steps.append({"step": "STARTTLS Encryption", "status": "PASS", "detail": "TLS v1.2/v1.3 session established"})
        else:
            steps.append({"step": "STARTTLS Encryption", "status": "SKIP", "detail": "SSL or TLS disabled"})
    except Exception as err:
        steps.append({"step": "STARTTLS Encryption", "status": "FAIL", "detail": str(err)})
        server_obj.close()
        return {"success": False, "stage": "TLS Handshake", "message": f"TLS Negotiation failed: {err}", "steps": steps}

    # 4. Authentication
    try:
        server_obj.login(cfg['user'], cfg['password'])
        steps.append({"step": "SMTP Authentication", "status": "PASS", "detail": f"Authenticated as {masked_user}"})
    except smtplib.SMTPAuthenticationError as auth_err:
        steps.append({"step": "SMTP Authentication", "status": "FAIL", "detail": f"SMTP 535: {auth_err.smtp_error.decode('utf-8', errors='ignore') if isinstance(auth_err.smtp_error, bytes) else str(auth_err)}"})
        server_obj.close()
        return {
            "success": False,
            "stage": "Authentication",
            "message": "SMTP authentication failed (Code 535). Please verify your Gmail address and 16-character Google App Password.",
            "steps": steps
        }
    except Exception as err:
        steps.append({"step": "SMTP Authentication", "status": "FAIL", "detail": str(err)})
        server_obj.close()
        return {"success": False, "stage": "Authentication", "message": f"Authentication error: {err}", "steps": steps}

    # 5. Optional Submission Test
    if to_email:
        try:
            msg = MIMEMultipart('alternative')
            msg['Subject'] = "Welcome to TalentSphere Learning Platform 🎓"
            msg['From'] = f"{cfg['sender_name']} <{cfg['sender']}>"
            msg['To'] = to_email
            
            try:
                body = render_template('emails/welcome.html', trainee_name="Asritha", email=to_email, temporary_password="asritha", login_url="http://localhost:5000/login")
            except Exception:
                body = f"""
                <!DOCTYPE html>
                <html>
                <body style="margin: 0; padding: 0; background-color: #f1f5f9; font-family: 'Segoe UI', Arial, sans-serif; color: #334155;">
                    <table border="0" cellpadding="0" cellspacing="0" width="100%" style="padding: 30px 10px;">
                        <tr><td align="center">
                            <table border="0" cellpadding="0" cellspacing="0" width="100%" style="max-width: 650px; background-color: #ffffff; border-radius: 8px; overflow: hidden; border: 1px solid #e2e8f0;">
                                <tr>
                                    <td style="background-color: #2563eb; padding: 25px 20px; text-align: center;">
                                        <h2 style="color: #ffffff; margin: 0; font-size: 22px; font-weight: 700;">Welcome to TalentSphere Learning Platform 🎓</h2>
                                    </td>
                                </tr>
                                <tr>
                                    <td style="padding: 35px 35px 25px 35px; line-height: 1.6; font-size: 15px;">
                                        <p style="margin: 0 0 20px 0;">Hi <strong>Asritha</strong>,</p>
                                        <p style="margin: 0 0 20px 0;">Your account has been created by an administrator. Here are your login credentials:</p>
                                        <table border="0" cellpadding="14" cellspacing="0" width="100%" style="background-color: #f8fafc; border: 1px solid #e2e8f0; border-radius: 6px; margin: 25px 0; font-size: 14px;">
                                            <tr style="border-bottom: 1px solid #f1f5f9;">
                                                <td width="30%" style="font-weight: 700; color: #0f172a;">Login Email</td>
                                                <td style="color: #2563eb;"><a href="mailto:{to_email}" style="color: #2563eb; text-decoration: none;">{to_email}</a></td>
                                            </tr>
                                            <tr>
                                                <td style="font-weight: 700; color: #0f172a;">Password</td>
                                                <td style="color: #0f172a; font-family: monospace; font-size: 15px; font-weight: 600;">asritha</td>
                                            </tr>
                                        </table>
                                        <p style="margin: 20px 0 15px 0;">Please log in and change your password after your first sign-in for security.</p>
                                        <p style="margin: 0 0 25px 0; color: #64748b; font-size: 14px;">If you did not expect this email, please contact your administrator.</p>
                                        <p style="margin: 0 0 20px 0; font-weight: 700; color: #0f172a;">Thank you for joining TalentSphere Learning Platform!</p>
                                        <p style="margin: 0; color: #475569;">Best regards,<br><strong>TalentSphere Learning Platform</strong></p>
                                    </td>
                                </tr>
                            </table>
                        </td></tr>
                    </table>
                </body>
                </html>
                """
            msg.attach(MIMEText(body, 'html'))
            server_obj.sendmail(cfg['sender'], [to_email], msg.as_string())
            steps.append({"step": "Email Submission", "status": "PASS", "detail": f"Test message submitted to {to_email}"})
        except Exception as err:
            steps.append({"step": "Email Submission", "status": "FAIL", "detail": str(err)})
            server_obj.close()
            return {"success": False, "stage": "Submission", "message": f"Message submission failed: {err}", "steps": steps}
        finally:
            try:
                server_obj.quit()
            except Exception:
                pass
    else:
        try:
            server_obj.quit()
        except Exception:
            pass

    return {
        "success": True,
        "stage": "Complete",
        "message": "✓ SMTP Diagnostic Successful. All connection and authentication checks passed.",
        "steps": steps
    }

def send_email(to_email, subject, html_body, email_type="general", is_async=None):
    """
    Sends an HTML email via SMTP with logging in EmailLog.
    Supports both synchronous execution and background threading based on is_async / Config.EMAIL_ASYNC.
    """
    if is_async is None:
        is_async = Config.EMAIL_ASYNC

    if is_async:
        def worker():
            from app import app
            with app.app_context():
                _execute_send(to_email, subject, html_body, email_type)
        threading.Thread(target=worker, daemon=True).start()
        return True, "Email queued for background delivery."
    else:
        return _execute_send(to_email, subject, html_body, email_type)

def _execute_send(to_email, subject, html_body, email_type):
    from app import db

    log_entry = EmailLog(
        to_email=to_email,
        subject=subject,
        email_type=email_type,
        status='PENDING',
        retry_count=0
    )
    try:
        db.session.add(log_entry)
        db.session.commit()
    except Exception:
        db.session.rollback()

    cfg = get_smtp_config()

    if not cfg['user'] or not cfg['password']:
        try:
            log_entry.status = 'FAILED'
            log_entry.error_message = "SMTP credentials missing in .env / Admin Settings."
            db.session.commit()
        except Exception:
            db.session.rollback()
        return False, "SMTP credentials missing in .env or Admin Settings."

    try:
        log_entry.status = 'SENDING'
        db.session.commit()
    except Exception:
        db.session.rollback()

    msg = MIMEMultipart('alternative')
    msg['Subject'] = subject
    msg['From'] = f"{cfg['sender_name']} <{cfg['sender']}>"
    msg['To'] = to_email
    msg.attach(MIMEText(html_body, 'html'))

    max_retries = 3
    last_error = ""

    for attempt in range(1, max_retries + 1):
        log_entry.retry_count = attempt
        try:
            if cfg['port'] == 465 or cfg['use_ssl']:
                server = smtplib.SMTP_SSL(cfg['server'], cfg['port'], timeout=15)
            else:
                server = smtplib.SMTP(cfg['server'], cfg['port'], timeout=15)
                if cfg['use_tls']:
                    server.starttls()

            if cfg['password']:
                server.login(cfg['user'], cfg['password'])

            server.sendmail(cfg['sender'], [to_email], msg.as_string())
            server.quit()

            log_entry.status = 'SENT'
            log_entry.sent_at = datetime.utcnow()
            log_entry.error_message = None
            db.session.commit()
            print(f"[Email Success] '{email_type}' email delivered to {to_email}")
            return True, f"Email delivered to {to_email}"
        except smtplib.SMTPAuthenticationError as err:
            last_error = f"SMTP 535 Authentication Error: Verify Gmail App Password. ({err})"
            print(f"[SMTP Auth Error] {last_error}")
            break
        except Exception as err:
            last_error = str(err)
            print(f"[SMTP Attempt {attempt} Error] {err}")
            time.sleep(1)

    log_entry.status = 'FAILED'
    log_entry.error_message = f"Failed after {log_entry.retry_count} attempts: {last_error}"
    db.session.commit()
    return False, last_error

# --------------------------------------------------------------------------
# HIGH LEVEL SPECIFIC EMAIL FUNCTIONS
# --------------------------------------------------------------------------

def render_corporate_email_html(title, greeting_name, body_html, cta_text="", cta_url="", accent_color="#2563eb"):
    cta_html = ""
    if cta_text and cta_url:
        cta_html = f"""
        <div style="text-align: center; margin: 30px 0;">
            <a href="{cta_url}" style="background-color: #2563eb; color: #ffffff; padding: 14px 32px; text-decoration: none; border-radius: 8px; font-weight: bold; font-size: 15px; display: inline-block; box-shadow: 0 4px 6px rgba(0,0,0,0.1);">
                {cta_text}
            </a>
        </div>
        """

    return f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="utf-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>{title}</title>
    </head>
    <body style="margin: 0; padding: 0; background-color: #f1f5f9; font-family: 'Segoe UI', Arial, sans-serif; color: #334155;">
        <table border="0" cellpadding="0" cellspacing="0" width="100%" style="table-layout: fixed; padding: 30px 10px;">
            <tr>
                <td align="center">
                    <table border="0" cellpadding="0" cellspacing="0" width="100%" style="max-width: 650px; background-color: #ffffff; border-radius: 8px; overflow: hidden; border: 1px solid #e2e8f0; box-shadow: 0 4px 15px rgba(0,0,0,0.05);">
                        <tr>
                            <td style="background-color: #2563eb; padding: 25px 20px; text-align: center;">
                                <h2 style="color: #ffffff; margin: 0; font-size: 22px; font-weight: 700;">{title}</h2>
                            </td>
                        </tr>
                        <tr>
                            <td style="padding: 35px 35px 25px 35px; line-height: 1.6; color: #1e293b; font-size: 15px;">
                                <p style="margin: 0 0 20px 0; font-size: 15px;">Hi <strong>{greeting_name}</strong>,</p>
                                {body_html}
                                {cta_html}
                                <p style="margin: 25px 0 0 0; font-weight: 700; color: #0f172a; font-size: 15px;">
                                    Thank you for joining TalentSphere Learning Platform!
                                </p>
                                <p style="margin: 15px 0 0 0; color: #475569;">
                                    Best regards,<br>
                                    <strong>TalentSphere Learning Platform</strong>
                                </p>
                            </td>
                        </tr>
                    </table>
                </td>
            </tr>
        </table>
    </body>
    </html>
    """

def send_welcome_email(user_email, name, temp_password, login_url="http://localhost:5000/login"):
    subject = "Welcome to TalentSphere Learning Platform 🎓"
    try:
        html_content = render_template('emails/welcome.html', trainee_name=name, email=user_email, temporary_password=temp_password, login_url=login_url)
    except Exception:
        body_html = f"""
        <p>Hi <strong>{name}</strong>,</p>
        <p>Your account has been created by an administrator. Here are your login credentials:</p>
        <table border="0" cellpadding="10" cellspacing="0" width="100%" style="background-color: #f8fafc; border: 1px solid #e2e8f0; border-radius: 6px; margin: 20px 0; font-size: 14px;">
            <tr><td style="font-weight: 700; color: #0f172a;">Login Email</td><td style="color: #2563eb;">{user_email}</td></tr>
            <tr><td style="font-weight: 700; color: #0f172a;">Password</td><td style="font-weight: 600; font-family: monospace;">{temp_password}</td></tr>
        </table>
        <p>Please log in and change your password after your first sign-in for security.</p>
        <p>If you did not expect this email, please contact your administrator.</p>
        <p><strong>Thank you for joining TalentSphere Learning Platform!</strong></p>
        <p>Best regards,<br><strong>TalentSphere Learning Platform</strong></p>
        """
        html_content = render_corporate_email_html(subject, name, body_html, "LOGIN TO TALENTSPHERE", login_url, "#2563eb")
    return send_email(user_email, subject, html_content, 'ACCOUNT_CREATED')

def send_temp_credentials_email(user_email, employee_id, name, temp_password, login_url, learning_path_title="Enterprise Training Path"):
    return send_welcome_email(user_email, name, temp_password, login_url)

def send_password_reset_email(user_email, name, reset_url):
    subject = "Password Reset Request - TalentSphere Learning Platform"
    body_html = f"""
    <p>We received a request to reset the password for your TalentSphere account associated with <strong>{user_email}</strong>.</p>
    <p>Click the button below to set a new password. This link will expire in 60 minutes.</p>
    """
    html_content = render_corporate_email_html(subject, name, body_html, "Reset Password", reset_url, "#0284C7")
    return send_email(user_email, subject, html_content, 'PASSWORD_RESET')

def send_learning_path_assigned_email(user_email, name, path_title, path_url="http://localhost:5000/trainee/roadmap"):
    subject = f"New Learning Path Assigned: {path_title}"
    body_html = f"""
    <p>Your administrator has assigned a new learning path to your profile: <strong>{path_title}</strong>.</p>
    """
    html_content = render_corporate_email_html(subject, name, body_html, "View Learning Path", path_url, "#059669")
    return send_email(user_email, subject, html_content, 'LEARNING_PATH')

def send_exam_assigned_email(user_email, user_name, exam_name, week_number=1, day_number=5, duration_minutes=30, passing_marks=70, due_date="Upcoming", exam_url="http://localhost:5000/trainee/exams"):
    subject = f"New Exam Assigned: {exam_name}"
    body_html = f"""
    <p>A new exam <strong>"{exam_name}"</strong> has been assigned to you.</p>
    <table border="0" cellpadding="10" cellspacing="0" width="100%" style="background-color: #f8fafc; border: 1px solid #e2e8f0; border-radius: 8px; margin: 15px 0; font-size: 14px;">
        <tr><td style="font-weight: 600; color: #64748b;">Module:</td><td>Week {week_number}, Day {day_number}</td></tr>
        <tr><td style="font-weight: 600; color: #64748b;">Duration:</td><td>{duration_minutes} Minutes</td></tr>
        <tr><td style="font-weight: 600; color: #64748b;">Passing Score:</td><td>{passing_marks}%</td></tr>
        <tr><td style="font-weight: 600; color: #64748b;">Due Date:</td><td style="color: #dc2626; font-weight: 700;">{due_date}</td></tr>
    </table>
    """
    html_content = render_corporate_email_html(subject, user_name, body_html, "Start Exam", exam_url, "#0284C7")
    return send_email(user_email, subject, html_content, 'EXAM_ASSIGNED')

def send_exam_reminder_email(user_email, user_name, exam_name, timeframe_text="24 Hours", due_date_str="Upcoming", exam_url="http://localhost:5000/trainee/exams"):
    subject = f"⏰ URGENT REMINDER: Exam '{exam_name}' Due in {timeframe_text}"
    body_html = f"""
    <p style="color: #dc2626; font-weight: 700;">Your exam deadline is approaching!</p>
    <p>Exam <strong>{exam_name}</strong> is due in <strong>{timeframe_text}</strong> ({due_date_str}).</p>
    """
    html_content = render_corporate_email_html(subject, user_name, body_html, "Complete Exam Now", exam_url, "#ea580c")
    return send_email(user_email, subject, html_content, 'EXAM_DEADLINE')

def send_exam_published_email(user_email, user_name, exam_name, week_number=1, exam_url="http://localhost:5000/trainee/exams"):
    return send_exam_assigned_email(user_email, user_name, exam_name, week_number=week_number, exam_url=exam_url)

def send_results_released_email(user_email, user_name, exam_name, score=85, percentage=85.0, status="Passed", result_url="http://localhost:5000/trainee/exams"):
    subject = f"Exam Results Released: {exam_name}"
    body_html = f"""
    <p>Your results for <strong>"{exam_name}"</strong> are now available.</p>
    <div style="background-color: #f8fafc; padding: 15px; border-radius: 8px; text-align: center;">
        <div style="font-size: 28px; font-weight: 800; color: #0F766E;">{percentage}%</div>
        <div style="font-weight: 700; color: #166534;">Status: {status}</div>
    </div>
    """
    html_content = render_corporate_email_html(subject, user_name, body_html, "View Results", result_url, "#0F766E")
    return send_email(user_email, subject, html_content, 'RESULTS_RELEASED')

def send_announcement_email(user_email, user_name, announcement_title, content_snippet, announcement_url="http://localhost:5000/trainee/dashboard"):
    subject = f"📢 Announcement: {announcement_title}"
    body_html = f"<p><strong>{announcement_title}</strong></p><p>{content_snippet}</p>"
    html_content = render_corporate_email_html(subject, user_name, body_html, "Read Announcement", announcement_url, "#2563eb")
    return send_email(user_email, subject, html_content, 'ANNOUNCEMENT')

def send_mock_interview_scheduled_email(user_email, user_name, week_title="Week 1 Viva", scheduled_time="Today", interview_url="http://localhost:5000/trainee/roadmap"):
    subject = f"🎙️ AI Mock Interview Scheduled: {week_title}"
    body_html = f"<p>Your Day 6 AI Mock Interview for <strong>{week_title}</strong> is ready.</p>"
    html_content = render_corporate_email_html(subject, user_name, body_html, "Enter Interview Room", interview_url, "#9333ea")
    return send_email(user_email, subject, html_content, 'MOCK_INTERVIEW')

def send_certificate_email(user_email, user_name, path_title="Enterprise Training Path", certificate_code="CERT-9988", issue_date_str="Today", cert_url="http://localhost:5000/trainee/dashboard"):
    subject = f"🎓 Certificate Issued for {path_title}"
    body_html = f"<p>Congratulations! Your official certificate code is <strong>{certificate_code}</strong>.</p>"
    html_content = render_corporate_email_html(subject, user_name, body_html, "View Certificate", cert_url, "#16a34a")
    return send_email(user_email, subject, html_content, 'CERTIFICATE')
