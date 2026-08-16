# TalentSphere Learning Platform

Enterprise AI-Powered Training Management System built with Python Flask, SQLAlchemy, ChromaDB, LangChain, and Groq API.

## Features
- **Strict Role-Based Access Control**: Separate Admin and Trainee portals.
- **6-Week Progressive Curriculum**: Days 1–4 Lessons, Day 5 AI Exam, Day 6 AI Mock Interview.
- **Same-Tab Embedded PDF Viewer**: PDF.js canvas viewer with zoom, search, bookmarks, and completion tracking.
- **Security-Guarded RAG Pipeline**: Trainee AI Chatbot retrieves answers ONLY from assigned, unlocked documents using `$and` metadata filters.
- **Google Mail SMTP Delivery**: Asynchronous HTML emails for credentials, exam notices, deadline reminders (7d, 3d, 1d, 1h), and certificates.

## Quickstart Setup

1. **Clone repository & set virtual environment**:
   ```bash
   python -m venv venv
   .\venv\Scripts\activate
   pip install -r requirements.txt
   ```

2. **Configure environment**:
   ```bash
   cp .env.example .env
   ```

3. **Launch Server**:
   ```bash
   python run.py
   ```
   👉 Open browser: `http://localhost:5000`

## Production Deployment (Docker Compose)

```bash
docker-compose up -d --build
```
