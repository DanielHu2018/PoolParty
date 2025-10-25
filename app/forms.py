from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, BooleanField, SubmitField, IntegerField, TextAreaField, DateTimeField, ValidationError
from wtforms.validators import DataRequired, Email, EqualTo, Length, NumberRange, Optional
from .models import User


class RegistrationForm(FlaskForm):
    username = StringField('Username', validators=[DataRequired(), Length(min=3, max=64)])
    email = StringField('Email', validators=[DataRequired(), Email(), Length(max=120)])
    password = PasswordField('Password', validators=[DataRequired(), Length(min=6)])
    password2 = PasswordField('Repeat Password', validators=[DataRequired(), EqualTo('password')])
    full_name = StringField('Full name', validators=[Optional(), Length(max=128)])
    phone = StringField('Phone', validators=[Optional(), Length(max=32)])
    submit = SubmitField('Register')

    def validate_username(self, username):
        # ensure username is unique
        if User.query.filter_by(username=username.data).first():
            raise ValidationError('That username is already taken. Please choose another.')

    def validate_email(self, email):
        # ensure email is unique
        if User.query.filter_by(email=email.data).first():
            raise ValidationError('An account with that email already exists.')


class LoginForm(FlaskForm):
    username = StringField('Username', validators=[DataRequired()])
    password = PasswordField('Password', validators=[DataRequired()])
    remember_me = BooleanField('Remember me')
    submit = SubmitField('Sign In')


class PoolForm(FlaskForm):
    title = StringField('Title', validators=[DataRequired(), Length(max=140)])
    origin = StringField('Origin', validators=[DataRequired(), Length(max=140)])
    destination = StringField('Destination', validators=[DataRequired(), Length(max=140)])
    depart_time = DateTimeField('Departure time (YYYY-mm-dd HH:MM)', format='%Y-%m-%d %H:%M', validators=[Optional()])
    seats = IntegerField('Seats', default=1, validators=[DataRequired(), NumberRange(min=1, max=10)])
    description = TextAreaField('Description', validators=[Optional(), Length(max=2000)])
    submit = SubmitField('Create Pool')


class JoinRequestForm(FlaskForm):
    message = TextAreaField('Message', validators=[Optional(), Length(max=500)])
    submit = SubmitField('Request to Join')


class ProfileForm(FlaskForm):
    full_name = StringField('Full name', validators=[Optional(), Length(max=128)])
    phone = StringField('Phone', validators=[Optional(), Length(max=32)])
    pickup_address = StringField('Pickup address', validators=[Optional(), Length(max=255)])
    pickup_notes = TextAreaField("Pickup notes (landmarks, gate codes, where you'll wait)", validators=[Optional(), Length(max=500)])
    appearance = StringField('Appearance (clothing, hair, etc)', validators=[Optional(), Length(max=255)])
    submit = SubmitField('Save')
