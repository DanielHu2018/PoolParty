from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, BooleanField, SubmitField, IntegerField, TextAreaField, DateTimeField
from wtforms.validators import DataRequired, Email, EqualTo, Length, NumberRange, Optional


class RegistrationForm(FlaskForm):
    username = StringField('Username', validators=[DataRequired(), Length(min=3, max=64)])
    email = StringField('Email', validators=[DataRequired(), Email(), Length(max=120)])
    password = PasswordField('Password', validators=[DataRequired(), Length(min=6)])
    password2 = PasswordField('Repeat Password', validators=[DataRequired(), EqualTo('password')])
    full_name = StringField('Full name', validators=[Optional(), Length(max=128)])
    phone = StringField('Phone', validators=[Optional(), Length(max=32)])
    submit = SubmitField('Register')


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
    submit = SubmitField('Save')
