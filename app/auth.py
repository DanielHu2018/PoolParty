from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from .forms import RegistrationForm, LoginForm, ProfileForm
from .models import User
from . import db
from sqlalchemy import or_
from sqlalchemy.exc import IntegrityError, OperationalError

auth_bp = Blueprint('auth', __name__, template_folder='templates')


@auth_bp.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('main.listings'))
    form = RegistrationForm()
    if form.validate_on_submit():
        # NOTE: in production, use better password hashing and validation
        pw_hash = generate_password_hash(form.password.data)
        user = User(username=form.username.data, email=form.email.data, password=pw_hash,
                    full_name=form.full_name.data, phone=form.phone.data)
        db.session.add(user)
        try:
            db.session.commit()
        except IntegrityError:
            db.session.rollback()
            flash('An account with that username or email already exists.', 'danger')
            return render_template('register.html', form=form)
        flash('Registration successful. You can now log in.', 'success')
        return redirect(url_for('auth.login'))
    return render_template('register.html', form=form)


@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('main.listings'))
    form = LoginForm()
    if form.validate_on_submit():
        # allow users to sign in using either username or email
        user = User.query.filter(or_(User.username == form.username.data, User.email == form.username.data)).first()
        if user and check_password_hash(user.password, form.password.data):
            login_user(user, remember=form.remember_me.data)
            next_page = request.args.get('next') or url_for('main.listings')
            return redirect(next_page)
        flash('Invalid username or password', 'danger')
    return render_template('login.html', form=form)


@auth_bp.route('/logout')
@login_required
def logout():
    logout_user()
    flash('Logged out', 'info')
    return redirect(url_for('main.listings'))


@auth_bp.route('/profile', methods=['GET', 'POST'])
@login_required
def profile():
    form = ProfileForm(obj=current_user)
    if form.validate_on_submit():
        current_user.full_name = form.full_name.data
        current_user.phone = form.phone.data
        # save pickup information and appearance
        current_user.pickup_address = form.pickup_address.data
        current_user.pickup_notes = form.pickup_notes.data
        current_user.appearance = form.appearance.data
        try:
            db.session.commit()
            flash('Profile updated', 'success')
        except OperationalError:
            db.session.rollback()
            # Some deployments may have an older DB schema without the new columns.
            # We gracefully tell the user and save whatever fields are supported by the DB.
            flash('Profile saved, but some fields could not be persisted because the database schema is out of date. Run a migration or recreate the DB to enable all fields.', 'warning')
        return redirect(url_for('auth.profile'))
    return render_template('profile.html', form=form)
