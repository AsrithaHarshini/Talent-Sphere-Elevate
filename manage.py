import sys
import argparse
from app import app
from email_service import test_smtp_connection, get_smtp_config

def run_smtp_diagnostic(target_email):
    print("=" * 60)
    print("TalentSphere Learning Platform - SMTP Diagnostic Tool")
    print("=" * 60)

    cfg = get_smtp_config()
    masked_user = f"{cfg['user'][:2]}*****@{cfg['user'].split('@')[-1]}" if '@' in cfg['user'] else "Unconfigured"
    masked_target = f"{target_email[:2]}*****@{target_email.split('@')[-1]}" if '@' in target_email else target_email

    print(f"SMTP Host: {cfg['server']}")
    print(f"SMTP Port: {cfg['port']}")
    print(f"TLS Enabled: {cfg['use_tls']}")
    print(f"Sender Account: {masked_user}")
    print(f"Target Recipient: {masked_target}")
    print("-" * 60)

    with app.app_context():
        res = test_smtp_connection(to_email=target_email)

    for i, step in enumerate(res['steps'], 1):
        print(f"[{i}] {step['step']:<28} ... [{step['status']:<4}] {step['detail']}")

    print("=" * 60)
    if res['success']:
        print("RESULT:")
        safe_msg = str(res['message']).encode('ascii', 'ignore').decode()
        print(f"SUCCESS: {safe_msg}")
        print(f"Please check {target_email} Inbox, Spam, Promotions, or Updates folder.")
        sys.exit(0)
    else:
        print("RESULT:")
        print(f"FAILURE: {res['message']}")
        print(f"Diagnostic Failure Stage: {res['stage']}")
        sys.exit(1)

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="TalentSphere Management CLI")
    subparsers = parser.add_subparsers(dest='command')

    test_email_parser = subparsers.add_parser('test-email', help="Run SMTP Diagnostic and send test email")
    test_email_parser.add_argument('--to', required=True, help="Recipient Gmail address for test delivery")

    args = parser.parse_args()

    if args.command == 'test-email':
        run_smtp_diagnostic(args.to)
    else:
        parser.print_help()
