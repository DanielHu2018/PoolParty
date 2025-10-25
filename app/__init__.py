from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from config import Config

db = SQLAlchemy()
login_manager = LoginManager()
login_manager.login_view = 'auth.login'


def create_app(config_class=Config):
    app = Flask(__name__, instance_relative_config=False)
    app.config.from_object(config_class)

    db.init_app(app)
    login_manager.init_app(app)

    # register blueprints
    from .auth import auth_bp
    from .main import main_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(main_bp)

    # create database tables if they don't exist
    with app.app_context():
        db.create_all()

    return app
