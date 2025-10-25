from datetime import datetime
from flask_login import UserMixin
from . import db, login_manager


class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(64), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password = db.Column(db.String(128), nullable=False)
    full_name = db.Column(db.String(128))
    phone = db.Column(db.String(32))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    pools = db.relationship('Pool', backref='owner', lazy='dynamic')
    join_requests = db.relationship('JoinRequest', backref='requester', lazy='dynamic')

    def __repr__(self):
        return f'<User {self.username}>'


class Pool(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(140), nullable=False)
    origin = db.Column(db.String(140), nullable=False)
    destination = db.Column(db.String(140), nullable=False)
    depart_time = db.Column(db.DateTime, nullable=True)
    seats = db.Column(db.Integer, default=1)
    description = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    owner_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    join_requests = db.relationship('JoinRequest', backref='pool', lazy='dynamic')
    rides = db.relationship('Ride', backref='pool', lazy='dynamic')

    def __repr__(self):
        return f'<Pool {self.title} {self.origin}->{self.destination}>'


class JoinRequest(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    pool_id = db.Column(db.Integer, db.ForeignKey('pool.id'))
    message = db.Column(db.Text)
    status = db.Column(db.String(20), default='pending')  # pending/accepted/rejected
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f'<JoinRequest {self.user_id} -> {self.pool_id} ({self.status})>'


class Ride(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    pool_id = db.Column(db.Integer, db.ForeignKey('pool.id'))
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    status = db.Column(db.String(20), default='scheduled')  # scheduled/completed/cancelled
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    passenger = db.relationship('User')

    def __repr__(self):
        return f'<Ride {self.id} pool={self.pool_id} user={self.user_id}>'


@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))
