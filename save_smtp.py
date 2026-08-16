import sys
from app import app, db
from database import SystemSetting
from email_service import test_smtp_connection

if len(sys.argv) < 3:
    print("Usage: python save_smtp.py <gmail_address> <16_character_app_password>")
    sys.exit(1)

gmail_user = sys.argv[1].strip()
app_pwd = sys.argv[2].strip().replace(" ", "")

with app.app_context():
    SystemSetting.set_setting('smtp_server', 'smtp.gmail.com')
    SystemSetting.set_setting('smtp_port', '587')
    SystemSetting.set_setting('smtp_username', gmail_user)
    SystemSetting.set_setting('smtp_password', app_pwd)
    SystemSetting.set_setting('smtp_sender_email', gmail_user)
    SystemSetting.set_setting('smtp_use_tls', 'true')
    db.session.commit()
    print(f"✓ Saved SMTP credentials for {gmail_user} into database!")

    print("Running diagnostic connection test...")
    res = test_smtp_connection(to_email=gmail_user)
    if res['success']:
        print("SUCCESS! Test email delivered to", gmail_user)
    else:
        print("DIAGNOSTIC FAILURE STAGE:", res['stage'])
        print("MESSAGE:", res['message'])
