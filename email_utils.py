"""
Legacy Email Utilities Wrapper.
Forwards all email functions and diagnostics to email_service.py for centralized handling.
"""

from email_service import (
    get_smtp_config,
    test_smtp_connection,
    send_email,
    render_corporate_email_html,
    send_welcome_email,
    send_temp_credentials_email,
    send_password_reset_email,
    send_learning_path_assigned_email,
    send_exam_assigned_email,
    send_exam_reminder_email,
    send_exam_published_email,
    send_results_released_email,
    send_announcement_email,
    send_mock_interview_scheduled_email,
    send_certificate_email
)

def send_email_async(to_email, subject, html_body, email_type="general"):
    return send_email(to_email, subject, html_body, email_type=email_type, is_async=True)

def send_account_created_email(user_email, employee_id, name, temp_password, login_url):
    return send_temp_credentials_email(user_email, employee_id, name, temp_password, login_url)
