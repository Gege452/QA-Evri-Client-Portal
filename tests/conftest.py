import os
import sys
import pytest
from flask import Flask, redirect, url_for
from werkzeug.security import generate_password_hash

project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, project_root)

from extensions import db, csrf
from flask_wtf.csrf import generate_csrf
from routes.auth_routes import auth_bp
from routes.admin_routes import admin_bp
from routes.client_routes import client_bp
from routes.enquiry_routes import enquiry_bp
from routes.parcel_routes import parcel_bp
from models import Client, User


@pytest.fixture
def app():
    project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    app = Flask(__name__, template_folder=os.path.join(project_root, "templates"))
    app.config["TESTING"] = True
    app.config["SECRET_KEY"] = "test-secret-key"
    app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///:memory:"
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    app.config["WTF_CSRF_ENABLED"] = False

    db.init_app(app)
    csrf.init_app(app)
    app.jinja_env.globals["csrf_token"] = generate_csrf
    app.register_blueprint(auth_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(client_bp)
    app.register_blueprint(enquiry_bp)
    app.register_blueprint(parcel_bp)

    @app.route("/")
    def index():
        return redirect(url_for("auth.login"))

    with app.app_context():
        db.create_all()

    yield app

    with app.app_context():
        db.drop_all()


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def init_data(app):
    with app.app_context():
        admin_user = User(
            email="admin@evri.com",
            password_hash=generate_password_hash("adminpass"),
            role="admin",
            display_name="Admin Tester",
            must_reset_password=False,
            is_active=True,
        )
        db.session.add(admin_user)
        db.session.commit()

        client_record = Client(
            client_name="Test Client Ltd",
            short_name="TEST",
            status="Active",
            account_manager="Admin Tester",
            phone_number="01234567890",
            email="client@example.com",
            address_line_1="1 Test Lane",
            postcode="TE5 7ST",
            country="United Kingdom",
            allow_stop_and_return=True,
        )
        db.session.add(client_record)
        db.session.flush()

        client_user = User(
            email="client@example.com",
            password_hash=generate_password_hash("clientpass"),
            role="client",
            display_name="Client Tester",
            client_id=client_record.id,
            must_reset_password=False,
            is_active=True,
        )
        db.session.add(client_user)
        db.session.commit()

        return {
            "admin_user_id": admin_user.id,
            "client_record_id": client_record.id,
            "client_user_id": client_user.id,
        }
