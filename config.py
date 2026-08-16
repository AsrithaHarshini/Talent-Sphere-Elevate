import os
from dotenv import load_dotenv

basedir = os.path.abspath(os.path.dirname(__file__))
load_dotenv(os.path.join(basedir, '.env'))

class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'hard to guess string'
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL') or \
        'sqlite:///' + os.path.join(basedir, 'talentsphere.db')
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    UPLOAD_FOLDER = os.path.join(basedir, 'uploads')
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024 # 16 MB max
    CHROMA_DB_DIR = os.path.join(basedir, 'chromadb')
    LLM_PROVIDER = os.environ.get('LLM_PROVIDER', 'groq')
    GROQ_API_KEY = os.environ.get('GROQ_API_KEY')
    OPENAI_API_KEY = os.environ.get('OPENAI_API_KEY')
    # SMTP / Mail Configuration
    MAIL_SERVER = os.environ.get('MAIL_SERVER') or os.environ.get('SMTP_SERVER') or 'smtp.gmail.com'
    MAIL_PORT = int(os.environ.get('MAIL_PORT') or os.environ.get('SMTP_PORT') or 587)
    MAIL_USE_TLS = (os.environ.get('MAIL_USE_TLS') or os.environ.get('SMTP_USE_TLS') or 'True').lower() == 'true'
    MAIL_USE_SSL = (os.environ.get('MAIL_USE_SSL') or 'False').lower() == 'true'
    MAIL_USERNAME = os.environ.get('MAIL_USERNAME') or os.environ.get('SMTP_USERNAME') or ''
    MAIL_PASSWORD = os.environ.get('MAIL_PASSWORD') or os.environ.get('SMTP_PASSWORD') or ''
    MAIL_DEFAULT_SENDER = os.environ.get('MAIL_DEFAULT_SENDER') or os.environ.get('SMTP_SENDER_EMAIL') or MAIL_USERNAME
    MAIL_DEFAULT_SENDER_NAME = os.environ.get('MAIL_DEFAULT_SENDER_NAME', 'Talent Management Platform for Employee Performance and Career Growth')
    EMAIL_ASYNC = (os.environ.get('EMAIL_ASYNC', 'True')).lower() == 'true'

    # Legacy Aliases for Backwards Compatibility
    SMTP_SERVER = MAIL_SERVER
    SMTP_PORT = MAIL_PORT
    SMTP_USERNAME = MAIL_USERNAME
    SMTP_PASSWORD = MAIL_PASSWORD
    SMTP_SENDER_EMAIL = MAIL_DEFAULT_SENDER
