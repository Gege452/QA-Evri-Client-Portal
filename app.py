from functools import wraps
from flask import Flask, render_template, request, redirect, url_for, session, flash
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, timezone


app = Flask(__name__)

# In a real deployment, this should be stored in an environment variable.
app.config["SECRET_KEY"] = "dev-secret-key-change-later"

# SQLite database file will be created in the project folder.
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///evri_client_portal.db"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db = SQLAlchemy(app)

ENQUIRY_CATEGORIES = [
    "General enquiry",
    "Parcel not delivered",
    "Delivery delay",
    "Damaged parcel",
    "Incorrect tracking information",
    "Address issue",
    "Stop and return request",
    "Account issue",
    "Billing issue",
]

PARCEL_RELATED_CATEGORIES = [
    "Parcel not delivered",
    "Delivery delay",
    "Damaged parcel",
    "Incorrect tracking information",
    "Address issue",
    "Stop and return request",
]

class User(db.Model):
    """
    Stores login accounts for both admin and client users.
    Passwords are stored as hashes, not plain text.
    """

    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(20), nullable=False)  # admin or client
    display_name = db.Column(db.String(100), nullable=False)
    must_reset_password = db.Column(db.Boolean, default=False)
    is_active = db.Column(db.Boolean, default=True)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

class Enquiry(db.Model):
    """
    Stores the main enquiry/ticket raised by a client.
    The original subject and message stay on this table.
    Follow-up discussion is stored in EnquiryComment.
    """

    id = db.Column(db.Integer, primary_key=True)
    created_by_user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)

    category = db.Column(db.String(80), nullable=False)
    tracking_number = db.Column(db.String(50), nullable=True)
    subject = db.Column(db.String(150), nullable=False)
    message = db.Column(db.Text, nullable=False)

    status = db.Column(db.String(30), nullable=False, default="New")

    created_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    closed_at = db.Column(db.DateTime, nullable=True)

    created_by = db.relationship("User", backref="enquiries")


class EnquiryComment(db.Model):
    """
    Stores follow-up comments added to an enquiry.
    User ID 1 is reserved for system-generated comments.
    """

    id = db.Column(db.Integer, primary_key=True)
    enquiry_id = db.Column(db.Integer, db.ForeignKey("enquiry.id"), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)

    comment = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))

    enquiry = db.relationship("Enquiry", backref="comments")
    user = db.relationship("User", backref="enquiry_comments")

def login_required(view_function):
    """
    Protects routes so only logged-in users can access them.
    """

    @wraps(view_function)
    def wrapper(*args, **kwargs):
        if "user_id" not in session:
            flash("Please log in to access the portal.", "error")
            return redirect(url_for("login"))

        return view_function(*args, **kwargs)

    return wrapper


def role_required(required_role):
    """
    Protects routes based on the user's role.
    Example: only admins can access /admin/home.
    """

    def decorator(view_function):
        @wraps(view_function)
        def wrapper(*args, **kwargs):
            if "user_id" not in session:
                flash("Please log in to access the portal.", "error")
                return redirect(url_for("login"))

            if session.get("role") != required_role:
                flash("You do not have permission to access that page.", "error")

                if session.get("role") == "admin":
                    return redirect(url_for("admin_home"))

                return redirect(url_for("client_home"))

            return view_function(*args, **kwargs)

        return wrapper

    return decorator

def create_database_and_seed_users():
    """
    Creates the database and inserts:
    - System user with ID 1
    - One admin test account
    - One client test account

    The system user is used for automated enquiry comments.
    """

    db.create_all()

    system_user = User.query.get(1)

    if not system_user:
        system_user = User(
            id=1,
            email="system@evri.local",
            password_hash=generate_password_hash("SystemAccountNotForLogin123!"),
            role="system",
            display_name="System",
            must_reset_password=False,
            is_active=False,
        )
        db.session.add(system_user)
        db.session.commit()

    admin_email = "admin"
    client_email = "client"

    existing_admin = User.query.filter_by(email=admin_email).first()
    existing_client = User.query.filter_by(email=client_email).first()

    if not existing_admin:
        admin_user = User(
            email=admin_email,
            password_hash=generate_password_hash("123"),
            role="admin",
            display_name="Admin User 1",
            must_reset_password=False,
            is_active=True,
        )
        db.session.add(admin_user)

    if not existing_client:
        client_user = User(
            email=client_email,
            password_hash=generate_password_hash("123"),
            role="client",
            display_name="Test Client Account",
            must_reset_password=False,
            is_active=True,
        )
        db.session.add(client_user)

    db.session.commit()


@app.route("/")
def index():
    return redirect(url_for("login"))


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")

        user = User.query.filter_by(email=email).first()

        if not user or not user.check_password(password):
            flash("Invalid email address or password.", "error")
            return redirect(url_for("login"))

        if not user.is_active:
            flash("This account is inactive. Please contact an administrator.", "error")
            return redirect(url_for("login"))

        session.clear()
        session["user_id"] = user.id
        session["email"] = user.email
        session["role"] = user.role
        session["display_name"] = user.display_name

        flash("Successfully logged in.", "success")

        if user.role == "admin":
            return redirect(url_for("admin_home"))

        return redirect(url_for("client_home"))

    return render_template("login.html")


@app.route("/client/home")
@role_required("client")
def client_home():
    return render_template(
        "home.html",
        portal_title="Client Portal",
        display_name=session.get("display_name"),
        email=session.get("email"),
        role="client",
    )

@app.route("/client/enquiry/new", methods=["GET", "POST"])
@role_required("client")
def new_client_enquiry():
    if request.method == "POST":
        category = request.form.get("category", "").strip()
        tracking_number = request.form.get("tracking_number", "").strip()
        subject = request.form.get("subject", "").strip()
        message = request.form.get("message", "").strip()

        errors = []

        if category not in ENQUIRY_CATEGORIES:
            errors.append("Please select a valid enquiry category.")

        if category in PARCEL_RELATED_CATEGORIES and not tracking_number:
            errors.append("Tracking number is required for parcel-related enquiries.")

        if not subject:
            errors.append("Subject is required.")

        if not message:
            errors.append("Message is required.")

        if errors:
            for error in errors:
                flash(error, "error")

            return render_template(
                "client/new_enquiry.html",
                categories=ENQUIRY_CATEGORIES,
                selected_category=category,
                tracking_number=tracking_number,
                subject=subject,
                message=message,
                email=session.get("email"),
            )

        now = datetime.now(timezone.utc)

        enquiry = Enquiry(
            created_by_user_id=session["user_id"],
            category=category,
            tracking_number=tracking_number if tracking_number else None,
            subject=subject,
            message=message,
            status="New",
            created_at=now,
            updated_at=now,
        )

        db.session.add(enquiry)
        db.session.commit()

        system_comment = EnquiryComment(
            enquiry_id=enquiry.id,
            user_id=1,
            comment=f"Enquiry ENQ{enquiry.id:06d} was created.",
            created_at=now,
        )

        db.session.add(system_comment)
        db.session.commit()

        flash(f"Enquiry ENQ{enquiry.id:06d} has been created successfully.", "success")
        return redirect(url_for("client_home"))

    return render_template(
        "client/new_enquiry.html",
        categories=ENQUIRY_CATEGORIES,
        selected_category="",
        tracking_number="",
        subject="",
        message="",
        email=session.get("email"),
    )

@app.route("/admin/home")
@role_required("admin")
def admin_home():
    return render_template(
        "home.html",
        portal_title="Admin Portal",
        display_name=session.get("display_name"),
        email=session.get("email"),
        role="admin",
    )


@app.route("/logout")
@login_required
def logout():
    session.clear()
    flash("Successfully logged out.", "success")
    return render_template("logout.html")


if __name__ == "__main__":
    with app.app_context():
        create_database_and_seed_users()

    app.run(debug=True)