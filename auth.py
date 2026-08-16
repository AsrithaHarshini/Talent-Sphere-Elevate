from flask import Blueprint, render_template, redirect, url_for, request, flash
from flask_login import login_user, logout_user, login_required, current_user
from database import db, User
from functools import wraps

auth_bp = Blueprint('auth', __name__)

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated:
            flash('Please log in to access this page.', 'info')
            return redirect(url_for('auth.login'))
        elif current_user.role != 'admin':
            flash('You do not have permission to access the admin portal.', 'danger')
            return redirect(url_for('trainee.dashboard'))
        return f(*args, **kwargs)
    return decorated_function

def trainee_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated:
            flash('Please log in to access this page.', 'info')
            return redirect(url_for('auth.login'))
        elif current_user.role != 'trainee':
            flash('You do not have permission to access the trainee portal.', 'danger')
            return redirect(url_for('admin.dashboard'))
        elif current_user.force_password_change:
            flash('Please update your temporary password to continue.', 'warning')
            return redirect(url_for('auth.change_password'))
        return f(*args, **kwargs)
    return decorated_function

@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        if getattr(current_user, 'force_password_change', False):
            return redirect(url_for('auth.change_password'))
        if current_user.role == 'admin':
            return redirect(url_for('admin.dashboard'))
        else:
            return redirect(url_for('trainee.dashboard'))

    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        
        user = User.query.filter_by(email=email).first()
        
        if user and user.check_password(password):
            if user.status != 'active':
                flash('Your account has been deactivated.', 'warning')
                return redirect(url_for('auth.login'))
                
            login_user(user)
            if getattr(user, 'force_password_change', False):
                flash('Temporary password detected. Please set a new secure password.', 'warning')
                return redirect(url_for('auth.change_password'))

            if user.role == 'admin':
                return redirect(url_for('admin.dashboard'))
            else:
                return redirect(url_for('trainee.dashboard'))
        else:
            flash('Please check your login details and try again.', 'danger')

    return render_template('login.html')

@auth_bp.route('/change-password', methods=['GET', 'POST'])
@login_required
def change_password():
    if request.method == 'POST':
        new_password = request.form.get('new_password')
        confirm_password = request.form.get('confirm_password')

        if not new_password or len(new_password) < 6:
            flash('Password must be at least 6 characters long.', 'danger')
            return render_template('change_password.html')

        if new_password != confirm_password:
            flash('Passwords do not match.', 'danger')
            return render_template('change_password.html')

        current_user.set_password(new_password)
        current_user.force_password_change = False
        db.session.commit()
        flash('Password updated successfully! Welcome to your training portal.', 'success')

        if current_user.role == 'admin':
            return redirect(url_for('admin.dashboard'))
        return redirect(url_for('trainee.dashboard'))

    return render_template('change_password.html')

@auth_bp.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('auth.login'))
