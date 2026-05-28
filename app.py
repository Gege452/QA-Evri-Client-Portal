from flask import Flask, redirect, url_for
import os

from extensions import db, csrf, limiter
from seed import create_database_and_seed_users
from flask_wtf.csrf import generate_csrf

from routes.auth_routes import auth_bp
from routes.admin_routes import admin_bp
from routes.client_routes import client_bp
from routes.enquiry_routes import enquiry_bp
from routes.parcel_routes import parcel_bp


def create_app():
    app = Flask(__name__)

    # Configuration
    app.config["SECRET_KEY"] = "dev-secret-key-change-later"
    app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///evri_client_portal.db"
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

    # Initialize extensions
    db.init_app(app)
    csrf.init_app(app)
    limiter.init_app(app)
    app.jinja_env.globals["csrf_token"] = generate_csrf

    # Register blueprints
    app.register_blueprint(auth_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(client_bp)
    app.register_blueprint(enquiry_bp)
    app.register_blueprint(parcel_bp)

    # Default route
    @app.route("/")
    def index():
        return redirect(url_for("auth.login"))
    
    # Create database and seed data
    with app.app_context():
        db.create_all()
        
        # Only seed data if not in testing mode to avoid conflicts with test database
        if not app.config.get("TESTING"):
            create_database_and_seed_users()

    return app

# Create the Flask application
app = create_app()

# Run the application
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)), debug=True)
