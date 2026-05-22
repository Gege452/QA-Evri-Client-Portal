from functools import wraps
import os
from flask import Flask, render_template, request, redirect, url_for, session, flash
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, timezone
import secrets
import string
from urllib.parse import quote


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
    client_id = db.Column(db.Integer, db.ForeignKey("client.id"), nullable=True)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(20), nullable=False)  # admin or client
    display_name = db.Column(db.String(100), nullable=False)
    must_reset_password = db.Column(db.Boolean, default=False)
    is_active = db.Column(db.Boolean, default=True)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

class Client(db.Model):
    """
    Stores client/company records managed by admin users.
    """

    id = db.Column(db.Integer, primary_key=True)
    client_name = db.Column(db.String(120), nullable=False)
    short_name = db.Column(db.String(20), nullable=False)
    status = db.Column(db.String(30), nullable=False, default="Pending")
    account_manager = db.Column(db.String(100), nullable=False)

    phone_number = db.Column(db.String(30), nullable=True)
    email = db.Column(db.String(120), nullable=True)

    address_line_1 = db.Column(db.String(120), nullable=True)
    address_line_2 = db.Column(db.String(120), nullable=True)
    address_line_3 = db.Column(db.String(120), nullable=True)
    address_line_4 = db.Column(db.String(120), nullable=True)
    postcode = db.Column(db.String(20), nullable=True)
    country = db.Column(db.String(80), nullable=True)

    allow_stop_and_return = db.Column(db.Boolean, default=False)

    created_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))

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

class Parcel(db.Model):
    """
    Stores parcel records created by client users.
    The current parcel status is stored here, while status history is stored in TrackEvent.
    """

    id = db.Column(db.Integer, primary_key=True)

    tracking_number = db.Column(db.String(40), unique=True, nullable=False)
    client_id = db.Column(db.Integer, db.ForeignKey("client.id"), nullable=False)
    created_by_user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)

    parcel_size = db.Column(db.String(50), nullable=False)
    delivery_speed = db.Column(db.String(50), nullable=False)

    parcel_contents = db.Column(db.String(32), nullable=False)
    parcel_value_gbp = db.Column(db.Float, nullable=False)

    recipient_first_name = db.Column(db.String(80), nullable=False)
    recipient_last_name = db.Column(db.String(80), nullable=False)

    recipient_address_line_1 = db.Column(db.String(120), nullable=False)
    recipient_address_line_2 = db.Column(db.String(120), nullable=True)
    recipient_address_line_3 = db.Column(db.String(120), nullable=True)
    recipient_address_line_4 = db.Column(db.String(120), nullable=True)
    recipient_postcode = db.Column(db.String(20), nullable=False)
    recipient_country = db.Column(db.String(80), nullable=False)

    status = db.Column(db.String(40), nullable=False, default="Label Generated")

    created_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))

    client = db.relationship("Client", backref="parcels")
    created_by = db.relationship("User", backref="created_parcels")


class TrackEvent(db.Model):
    """
    Stores parcel tracking history.
    """

    id = db.Column(db.Integer, primary_key=True)

    parcel_id = db.Column(db.Integer, db.ForeignKey("parcel.id"), nullable=False)

    event_status = db.Column(db.String(50), nullable=False)
    event_location = db.Column(db.String(100), nullable=False)
    event_description = db.Column(db.String(255), nullable=False)

    visible_to_client = db.Column(db.Boolean, nullable=False, default=True)

    created_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))

    parcel = db.relationship("Parcel", backref="track_events")

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

def generate_temporary_password(length=14):
    """
    Generates a temporary password for newly created client accounts.
    This is shown once to the admin and only the hash is stored.
    """

    characters = string.ascii_letters + string.digits + "!@#$%&*"
    return "".join(secrets.choice(characters) for _ in range(length))


def get_new_client_session_data():
    """
    Gets the draft client data from the Flask session.
    Used by the multi-step create client wizard.
    """

    return session.get("new_client", {})


def save_new_client_session_data(updated_data):
    """
    Updates the draft client data in the Flask session.
    """

    current_data = session.get("new_client", {})
    current_data.update(updated_data)
    session["new_client"] = current_data
    session.modified = True


def validate_required_fields(data, required_fields):
    """
    Simple reusable validation for required form fields.
    """

    errors = []

    for field_name, friendly_name in required_fields.items():
        if not data.get(field_name):
            errors.append(f"{friendly_name} is required.")

    return errors

def build_client_onboarding_mailto(created_client, created_user, temporary_password, admin_user_display_name):
    """
    Builds a mailto link for the admin to contact the newly created client.

    This does not send an email from the Flask application.
    It opens the admin user's default email client with the recipient,
    subject and message pre-filled.
    """

    email_subject = "EVRi Client Portal Account Created"

    email_body = f"""Hello {created_client.client_name},

    We would like to welcome you onboard and thank you for choosing EVRi as your delivery partner.
    
    We have created your account for the EVRi Client Portal, where you can easily manage your deliveries and enquiries.

    Client ID: {created_client.id}
    Email address: {created_user.email}
    Temporary password: {temporary_password}

    Client ID might be required when contacting our support team, so please keep it handy.

    Email address and temporary password can be used to log in to the portal for the first time. For security reasons, only the password hash is stored in our database, so we cannot retrieve the temporary password after this point.
    Please make sure you sign in and change your password as soon as possible.

    Kind regards,
    EVRi Admin Team
    {admin_user_display_name}
    """

    return (
        f"mailto:{created_user.email}"
        f"?subject={quote(email_subject)}"
        f"&body={quote(email_body)}"
    )

def generate_tracking_number():
    """
    Generates a prototype tracking number.
    In a real system, this would likely come from a dedicated parcel/label service.
    """

    random_part = "".join(secrets.choice(string.digits) for _ in range(15))
    return f"H{random_part}"


def create_initial_track_event(parcel):
    """
    Creates the first tracking event when a parcel record is created.
    """

    track_event = TrackEvent(
        parcel_id=parcel.id,
        event_status="Label Generated",
        event_location="Client Portal",
        event_description="Parcel record created and delivery label request generated.",
        visible_to_client=True,
        created_at=datetime.now(timezone.utc),
    )

    db.session.add(track_event)

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

    if Client.query.count() == 0:
        sample_clients = [
            Client(
                client_name="SuperShoes",
                short_name="SUSH",
                status="Active",
                account_manager="Jon White",
                phone_number="07123456789",
                email="contact@supershoes.com",
                address_line_1="1 Test Street",
                postcode="AB12 3CD",
                country="United Kingdom",
                allow_stop_and_return=True,
            ),
            Client(
                client_name="Perfect Tires",
                short_name="PERT",
                status="Inactive",
                account_manager="Jon White",
                phone_number="07123456780",
                email="contact@perfecttires.com",
                address_line_1="2 Test Street",
                postcode="AB12 4CD",
                country="United Kingdom",
                allow_stop_and_return=False,
            ),
            Client(
                client_name="W Hats and Accessories",
                short_name="WHAA",
                status="Pending",
                account_manager="Jon White",
                phone_number="07123456781",
                email="contact@whatsaccessories.com",
                address_line_1="3 Test Street",
                postcode="AB12 5CD",
                country="United Kingdom",
                allow_stop_and_return=False,
            ),
            Client(
                client_name="Diamond Supplies",
                short_name="DISU",
                status="Active",
                account_manager="Jon White",
                phone_number="07123456782",
                email="contact@diamondsupplies.com",
                address_line_1="4 Test Street",
                postcode="AB12 6CD",
                country="United Kingdom",
                allow_stop_and_return=True,
            ),
        ]

        db.session.add_all(sample_clients)

    db.session.commit()


def format_enquiry_number(enquiry_id):
    return f"ENQ{enquiry_id:06d}"


def add_system_comment(enquiry_id, comment_text):
    system_comment = EnquiryComment(
        enquiry_id=enquiry_id,
        user_id=1,
        comment=comment_text,
        created_at=datetime.now(timezone.utc),
    )
    db.session.add(system_comment)

def validate_password_strength(password):
    errors = []

    if len(password) < 8:
        errors.append("Password must be at least 8 characters long.")

    if not any(char.isupper() for char in password):
        errors.append("Password must contain at least one uppercase letter.")

    if not any(char.islower() for char in password):
        errors.append("Password must contain at least one lowercase letter.")

    if not any(char.isdigit() for char in password):
        errors.append("Password must contain at least one number.")

    if not any(char in "!@#$%&*" for char in password):
        errors.append("Password must contain at least one special character: ! @ # $ % & *")

    return errors


@app.route("/")
def index():
    return redirect(url_for("login"))

@app.route("/reset-password", methods=["GET", "POST"])
@login_required
def reset_password():
    user = User.query.get_or_404(session["user_id"])

    if request.method == "POST":
        new_password = request.form.get("new_password", "")
        confirm_password = request.form.get("confirm_password", "")

        errors = []

        if not new_password:
            errors.append("New password is required.")

        if not confirm_password:
            errors.append("Please confirm your new password.")

        if new_password and confirm_password and new_password != confirm_password:
            errors.append("New password and confirmation password do not match.")

        errors.extend(validate_password_strength(new_password))

        if user.check_password(new_password):
            errors.append("New password cannot be the same as the current password.")

        if errors:
            for error in errors:
                flash(error, "error")

            return redirect(url_for("reset_password"))

        user.password_hash = generate_password_hash(new_password)
        user.must_reset_password = False

        if hasattr(user, "updated_at"):
            user.updated_at = datetime.now(timezone.utc)

        db.session.commit()

        session.clear()

        flash("Password reset successfully. Please log in with your new password.", "success")
        return redirect(url_for("login"))

    return render_template(
        "reset_password.html",
        page_title="Reset Password",
        email=session.get("email"),
    )

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

        session["user_id"] = user.id
        session["email"] = user.email
        session["role"] = user.role
        session["display_name"] = user.display_name

        if user.must_reset_password:
            flash("You must reset your password before accessing the portal.", "error")
            return redirect(url_for("reset_password"))

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

@app.route("/admin/clients")
@role_required("admin")
def admin_clients():
    search_by = request.args.get("search_by", "client_id")
    search_value = request.args.get("search_value", "").strip()

    query = Client.query

    if search_value:
        if search_by == "client_id":
            if search_value.isdigit():
                query = query.filter(Client.id == int(search_value))
            else:
                query = query.filter(Client.id == -1)

        elif search_by == "client_name":
            query = query.filter(Client.client_name.ilike(f"%{search_value}%"))

        elif search_by == "short_name":
            query = query.filter(Client.short_name.ilike(f"%{search_value}%"))

        elif search_by == "status":
            query = query.filter(Client.status.ilike(f"%{search_value}%"))

    clients = query.order_by(Client.client_name.asc()).all()

    return render_template(
        "clients.html",
        clients=clients,
        role="admin",
        portal_title="Admin Portal",
        page_title="Clients",
        email=session.get("email"),
        active_page="clients",
        search_by=search_by,
        search_value=search_value,
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
        active_page="enquiries",
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

@app.route("/client/enquiries")
@role_required("client")
def client_enquiries():
    search_by = request.args.get("search_by", "enquiry_number")
    search_value = request.args.get("search_value", "").strip()

    query = Enquiry.query.filter_by(created_by_user_id=session["user_id"])

    if search_value:
        if search_by == "enquiry_number":
            if search_value.upper().startswith("ENQ"):
                search_value = search_value.upper().replace("ENQ", "")

            if search_value.isdigit():
                query = query.filter(Enquiry.id == int(search_value))
            else:
                query = query.filter(Enquiry.id == -1)

        elif search_by == "subject":
            query = query.filter(Enquiry.subject.ilike(f"%{search_value}%"))

    enquiries = query.order_by(Enquiry.created_at.desc()).all()

    return render_template(
        "enquiries.html",
        enquiries=enquiries,
        role="client",
        portal_title="Client Portal",
        page_title="Enquiries",
        active_page="enquiries",
        email=session.get("email"),
        search_by=search_by,
        search_value=search_value,
    )

@app.route("/admin/enquiries")
@role_required("admin")
def admin_enquiries():
    search_by = request.args.get("search_by", "enquiry_number")
    search_value = request.args.get("search_value", "").strip()

    query = Enquiry.query

    if search_value:
        if search_by == "enquiry_number":
            if search_value.upper().startswith("ENQ"):
                search_value = search_value.upper().replace("ENQ", "")

            if search_value.isdigit():
                query = query.filter(Enquiry.id == int(search_value))
            else:
                query = query.filter(Enquiry.id == -1)

        elif search_by == "subject":
            query = query.filter(Enquiry.subject.ilike(f"%{search_value}%"))

        elif search_by == "status":
            query = query.filter(Enquiry.status.ilike(f"%{search_value}%"))

    enquiries = query.order_by(Enquiry.created_at.desc()).all()

    return render_template(
        "enquiries.html",
        enquiries=enquiries,
        role="admin",
        portal_title="Admin Portal",
        page_title="Enquiries",
        active_page="enquiries",
        email=session.get("email"),
        search_by=search_by,
        search_value=search_value,
    )

@app.route("/client/enquiry/<int:enquiry_id>", methods=["GET", "POST"])
@role_required("client")
def client_view_enquiry(enquiry_id):
    enquiry = Enquiry.query.get_or_404(enquiry_id)

    # Client can only view their own enquiries.
    if enquiry.created_by_user_id != session["user_id"]:
        flash("You do not have permission to view that enquiry.", "error")
        return redirect(url_for("client_enquiries"))

    if request.method == "POST":
        action = request.form.get("action")
        comment_text = request.form.get("comment", "").strip()

        if action == "add_comment":
            if enquiry.status == "Closed":
                flash("This enquiry is closed and cannot be updated.", "error")
                return redirect(url_for("client_view_enquiry", enquiry_id=enquiry.id))

            if not comment_text:
                flash("Comment cannot be empty.", "error")
                return redirect(url_for("client_view_enquiry", enquiry_id=enquiry.id))

            comment = EnquiryComment(
                enquiry_id=enquiry.id,
                user_id=session["user_id"],
                comment=comment_text,
                created_at=datetime.now(timezone.utc),
            )

            old_status = enquiry.status

            if enquiry.status == "On Hold":
                enquiry.status = "Work in Progress"
                add_system_comment(
                    enquiry.id,
                    f"{session['display_name']} updated the enquiry status from {old_status} to Work in Progress.",
                )

            enquiry.updated_at = datetime.now(timezone.utc)

            db.session.add(comment)
            db.session.commit()

            flash("Comment added successfully.", "success")
            return redirect(url_for("client_view_enquiry", enquiry_id=enquiry.id))

        if action == "close_enquiry":
            old_status = enquiry.status

            enquiry.status = "Closed"
            enquiry.closed_at = datetime.now(timezone.utc)
            enquiry.updated_at = datetime.now(timezone.utc)

            add_system_comment(
                enquiry.id,
                f"{session['display_name']} updated the enquiry status from {old_status} to Closed.",
            )

            db.session.commit()

            flash("Enquiry closed successfully.", "success")
            return redirect(url_for("client_view_enquiry", enquiry_id=enquiry.id))

    comments = (
        EnquiryComment.query
        .filter_by(enquiry_id=enquiry.id)
        .order_by(EnquiryComment.created_at.desc())
        .all()
    )

    return render_template(
        "view_enquiry.html",
        enquiry=enquiry,
        comments=comments,
        enquiry_number=format_enquiry_number(enquiry.id),
        role="client",
        portal_title="Client Portal",
        page_title="View Enquiry",
        email=session.get("email"),
        active_page="enquiries",
        categories=ENQUIRY_CATEGORIES,
    )
    

@app.route("/admin/enquiry/<int:enquiry_id>", methods=["GET", "POST"])
@role_required("admin")
def admin_view_enquiry(enquiry_id):
    enquiry = Enquiry.query.get_or_404(enquiry_id)

    if request.method == "POST":
        action = request.form.get("action")
        now = datetime.now(timezone.utc)

        if action == "update_enquiry":
            old_status = enquiry.status

            category = request.form.get("category", "").strip()
            tracking_number = request.form.get("tracking_number", "").strip()
            subject = request.form.get("subject", "").strip()
            message = request.form.get("message", "").strip()
            status = request.form.get("status", "").strip()

            allowed_statuses = ["New", "Work in Progress", "On Hold", "Closed"]

            errors = []

            if category not in ENQUIRY_CATEGORIES:
                errors.append("Please select a valid enquiry category.")

            if category in PARCEL_RELATED_CATEGORIES and not tracking_number:
                errors.append("Tracking number is required for parcel-related enquiries.")

            if not subject:
                errors.append("Subject is required.")

            if not message:
                errors.append("Message is required.")

            if status not in allowed_statuses:
                errors.append("Please select a valid enquiry status.")

            if errors:
                for error in errors:
                    flash(error, "error")
                return redirect(url_for("admin_view_enquiry", enquiry_id=enquiry.id))

            enquiry.category = category
            enquiry.tracking_number = tracking_number if tracking_number else None
            enquiry.subject = subject
            enquiry.message = message
            enquiry.status = status
            enquiry.updated_at = now

            if status == "Closed":
                enquiry.closed_at = now
            else:
                enquiry.closed_at = None

            if old_status != status:
                add_system_comment(
                    enquiry.id,
                    f"{session['display_name']} updated the enquiry status from {old_status} to {status}.",
                )
            else:
                add_system_comment(
                    enquiry.id,
                    f"{session['display_name']} updated the enquiry details.",
                )

            db.session.commit()

            flash("Enquiry updated successfully.", "success")
            return redirect(url_for("admin_view_enquiry", enquiry_id=enquiry.id))

        if action == "add_comment":
            comment_text = request.form.get("comment", "").strip()

            if enquiry.status == "Closed":
                flash("This enquiry is closed and cannot be updated.", "error")
                return redirect(url_for("admin_view_enquiry", enquiry_id=enquiry.id))

            if not comment_text:
                flash("Comment cannot be empty.", "error")
                return redirect(url_for("admin_view_enquiry", enquiry_id=enquiry.id))

            comment = EnquiryComment(
                enquiry_id=enquiry.id,
                user_id=session["user_id"],
                comment=comment_text,
                created_at=now,
            )

            old_status = enquiry.status

            if enquiry.status == "New":
                enquiry.status = "Work in Progress"
                add_system_comment(
                    enquiry.id,
                    f"{session['display_name']} updated the enquiry status from {old_status} to Work in Progress.",
                )

            enquiry.updated_at = now

            db.session.add(comment)
            db.session.commit()

            flash("Comment added successfully.", "success")
            return redirect(url_for("admin_view_enquiry", enquiry_id=enquiry.id))

    comments = (
        EnquiryComment.query
        .filter_by(enquiry_id=enquiry.id)
        .order_by(EnquiryComment.created_at.desc())
        .all()
    )

    return render_template(
        "view_enquiry.html",
        enquiry=enquiry,
        comments=comments,
        enquiry_number=f"ENQ{enquiry.id:06d}",
        role="admin",
        portal_title="Admin Portal",
        page_title="View Enquiry",
        email=session.get("email"),
        active_page="enquiries",
        categories=ENQUIRY_CATEGORIES,
    )

@app.route("/admin/enquiry/<int:enquiry_id>/comment/<int:comment_id>/delete", methods=["POST"])
@role_required("admin")
def admin_delete_enquiry_comment(enquiry_id, comment_id):
    enquiry = Enquiry.query.get_or_404(enquiry_id)
    comment = EnquiryComment.query.get_or_404(comment_id)

    if comment.enquiry_id != enquiry.id:
        flash("Comment does not belong to this enquiry.", "error")
        return redirect(url_for("admin_view_enquiry", enquiry_id=enquiry.id))

    # Do not allow deletion of system-generated comments.
    if comment.user_id == 1:
        flash("System comments cannot be deleted.", "error")
        return redirect(url_for("admin_view_enquiry", enquiry_id=enquiry.id))

    db.session.delete(comment)

    enquiry.updated_at = datetime.now(timezone.utc)

    add_system_comment(
        enquiry.id,
        f"{session['display_name']} deleted a comment from this enquiry."
    )

    db.session.commit()

    flash("Comment deleted successfully.", "success")
    return redirect(url_for("admin_view_enquiry", enquiry_id=enquiry.id))

@app.route("/admin/client/create", methods=["GET", "POST"])
@role_required("admin")
def admin_create_client():
    step = request.args.get("step", "1")

    if not step.isdigit():
        step = 1
    else:
        step = int(step)

    if step < 1 or step > 5:
        step = 1

    form_data = get_new_client_session_data()

    # Prevent direct access to later steps if required previous data is missing
    if step == 2 and not form_data.get("client_name"):
        flash("Please complete client details first.", "error")
        return redirect(url_for("admin_create_client", step=1))

    if step == 3 and not form_data.get("address_line_1"):
        flash("Please complete the business address first.", "error")
        return redirect(url_for("admin_create_client", step=2))

    if step == 4 and not form_data.get("short_name"):
        flash("Please complete client settings first.", "error")
        return redirect(url_for("admin_create_client", step=3))

    if step == 5:
        created_client_id = session.get("created_client_id")
        temporary_password = session.get("created_client_temp_password")

        if not created_client_id or not temporary_password:
            flash("Please create a client first.", "error")
            return redirect(url_for("admin_create_client", step=1))

        created_client = Client.query.get_or_404(created_client_id)
        created_user = User.query.filter_by(client_id=created_client.id, role="client").first()

        mailto_link = build_client_onboarding_mailto(
            created_client,
            created_user,
            temporary_password,
            session.get("display_name"),
        )

        return render_template(
            "create_client.html",
            step=5,
            form_data=form_data,
            created_client=created_client,
            created_user=created_user,
            temporary_password=temporary_password,
            mailto_link=mailto_link,
            role="admin",
            portal_title="Admin Portal",
            page_title="Create Client",
            email=session.get("email"),
            active_page="clients",
        )

    if request.method == "POST":

        # Step 1: Client Details
        if step == 1:
            client_name = request.form.get("client_name", "").strip()
            phone_number = request.form.get("phone_number", "").strip()
            email = request.form.get("email", "").strip().lower()

            data = {
                "client_name": client_name,
                "phone_number": phone_number,
                "email": email,
            }

            errors = validate_required_fields(data, {
                "client_name": "Client name",
                "phone_number": "Phone number",
                "email": "Email address",
            })

            existing_user = User.query.filter_by(email=email).first()
            if existing_user:
                errors.append("A user account already exists with this email address.")

            existing_client_name = Client.query.filter(db.func.lower(Client.client_name) == client_name.lower()).first()
            if existing_client_name:
                errors.append("A client already exists with this client name.")

            if errors:
                for error in errors:
                    flash(error, "error")

                save_new_client_session_data(data)
                return redirect(url_for("admin_create_client", step=1))

            save_new_client_session_data(data)
            return redirect(url_for("admin_create_client", step=2))

        # Step 2: Business Address
        if step == 2:
            data = {
                "address_line_1": request.form.get("address_line_1", "").strip(),
                "address_line_2": request.form.get("address_line_2", "").strip(),
                "address_line_3": request.form.get("address_line_3", "").strip(),
                "address_line_4": request.form.get("address_line_4", "").strip(),
                "postcode": request.form.get("postcode", "").strip(),
                "country": request.form.get("country", "").strip(),
            }

            errors = validate_required_fields(data, {
                "address_line_1": "Address line 1",
                "postcode": "Post code",
                "country": "Country",
            })

            if errors:
                for error in errors:
                    flash(error, "error")

                save_new_client_session_data(data)
                return redirect(url_for("admin_create_client", step=2))

            save_new_client_session_data(data)
            return redirect(url_for("admin_create_client", step=3))

        # Step 3: Settings
        if step == 3:
            short_name = request.form.get("short_name", "").strip().upper()
            status = request.form.get("status", "").strip()
            allow_stop_and_return = request.form.get("allow_stop_and_return") == "yes"

            data = {
                "short_name": short_name,
                "status": status,
                "allow_stop_and_return": allow_stop_and_return,
            }

            errors = validate_required_fields(data, {
                "short_name": "Short name",
                "status": "Status",
            })

            if status not in ["Pending", "Active", "Inactive"]:
                errors.append("Please select a valid status.")
            
            existing_short_name = Client.query.filter(db.func.lower(Client.short_name) == short_name.lower()).first()
            if existing_short_name:
                errors.append("A client already exists with this short name.")

            if errors:
                for error in errors:
                    flash(error, "error")

                save_new_client_session_data(data)
                return redirect(url_for("admin_create_client", step=3))

            save_new_client_session_data(data)
            return redirect(url_for("admin_create_client", step=4))

        # Step 4: Confirm and create client
        if step == 4:
            form_data = get_new_client_session_data()

            required_before_create = {
                "client_name": "Client name",
                "phone_number": "Phone number",
                "email": "Email address",
                "address_line_1": "Address line 1",
                "postcode": "Post code",
                "country": "Country",
                "short_name": "Short name",
                "status": "Status",
            }

            errors = validate_required_fields(form_data, required_before_create)

            if errors:
                for error in errors:
                    flash(error, "error")
                return redirect(url_for("admin_create_client", step=1))

            existing_user = User.query.filter_by(email=form_data["email"]).first()
            if existing_user:
                flash("A user account already exists with this email address.", "error")
                return redirect(url_for("admin_create_client", step=1))
            
            existing_client_name = Client.query.filter(db.func.lower(Client.client_name) == form_data["client_name"].lower()).first()
            if existing_client_name:
                flash("A client already exists with this client name.", "error")
                return redirect(url_for("admin_create_client", step=1))

            existing_short_name = Client.query.filter(db.func.lower(Client.short_name) == form_data["short_name"].lower()).first()
            if existing_short_name:
                flash("A client already exists with this short name.", "error")
                return redirect(url_for("admin_create_client", step=3))

            now = datetime.now(timezone.utc)

            new_client = Client(
                client_name=form_data["client_name"],
                short_name=form_data["short_name"],
                status=form_data["status"],
                account_manager=session.get("display_name", "Admin User"),
                phone_number=form_data["phone_number"],
                email=form_data["email"],
                address_line_1=form_data["address_line_1"],
                address_line_2=form_data.get("address_line_2"),
                address_line_3=form_data.get("address_line_3"),
                address_line_4=form_data.get("address_line_4"),
                postcode=form_data["postcode"],
                country=form_data["country"],
                allow_stop_and_return=form_data.get("allow_stop_and_return", False),
                created_at=now,
                updated_at=now,
            )

            db.session.add(new_client)
            db.session.flush()  # Gives us new_client.id before commit

            temporary_password = generate_temporary_password()

            new_client_user = User(
                email=form_data["email"],
                password_hash=generate_password_hash(temporary_password),
                role="client",
                display_name=form_data["client_name"],
                client_id=new_client.id,
                must_reset_password=True,
                is_active=True,
            )

            db.session.add(new_client_user)
            db.session.commit()

            session["created_client_id"] = new_client.id
            session["created_client_temp_password"] = temporary_password

            # Clear the draft form data now that the client is created
            session.pop("new_client", None)
            session.modified = True

            flash("Successfully created the client.", "success")
            return redirect(url_for("admin_create_client", step=5))

    return render_template(
        "create_client.html",
        step=step,
        form_data=form_data,
        role="admin",
        portal_title="Admin Portal",
        page_title="Create Client",
        email=session.get("email"),
        active_page="clients",
    )

@app.route("/admin/account", methods=["GET", "POST"])
@role_required("admin")
def admin_account():
    user = User.query.get_or_404(session["user_id"])

    if request.method == "POST":
        new_email = request.form.get("new_email", "").strip().lower()
        confirm_email = request.form.get("confirm_email", "").strip().lower()

        errors = []

        if not new_email:
            errors.append("New email address is required.")

        if not confirm_email:
            errors.append("Please confirm the new email address.")

        if new_email and confirm_email and new_email != confirm_email:
            errors.append("New email address and confirmation email do not match.")

        existing_user = User.query.filter(
            User.email == new_email,
            User.id != user.id
        ).first()

        if existing_user:
            errors.append("This email address is already used by another account.")

        if errors:
            for error in errors:
                flash(error, "error")

            return redirect(url_for("admin_account"))

        user.email = new_email

        if hasattr(user, "updated_at"):
            user.updated_at = datetime.now(timezone.utc)

        db.session.commit()

        session["email"] = user.email

        flash("Account email address updated successfully.", "success")
        return redirect(url_for("admin_account"))

    return render_template(
        "account.html",
        user=user,
        role="admin",
        portal_title="Admin Portal",
        page_title="Account Information",
        email=session.get("email"),
        active_page="account",
        department="Client Onboarding and Management",
    )

@app.route("/client/account", methods=["GET", "POST"])
@role_required("client")
def client_account():
    user = User.query.get_or_404(session["user_id"])

    if not user.client_id:
        flash("No client account is linked to this user.", "error")
        return redirect(url_for("client_home"))

    client = Client.query.get_or_404(user.client_id)

    if request.method == "POST":
        new_email = request.form.get("new_email", "").strip().lower()
        confirm_email = request.form.get("confirm_email", "").strip().lower()

        new_phone_number = request.form.get("new_phone_number", "").strip()
        confirm_phone_number = request.form.get("confirm_phone_number", "").strip()

        address_line_1 = request.form.get("address_line_1", "").strip()
        address_line_2 = request.form.get("address_line_2", "").strip()
        address_line_3 = request.form.get("address_line_3", "").strip()
        address_line_4 = request.form.get("address_line_4", "").strip()
        postcode = request.form.get("postcode", "").strip()
        country = request.form.get("country", "").strip()

        errors = []

        # Email update is optional, but if one field is filled, both must match.
        if new_email or confirm_email:
            if not new_email:
                errors.append("New email address is required.")
            if not confirm_email:
                errors.append("Please confirm the new email address.")
            if new_email and confirm_email and new_email != confirm_email:
                errors.append("New email address and confirmation email do not match.")

            existing_user = User.query.filter(
                User.email == new_email,
                User.id != user.id
            ).first()

            if existing_user:
                errors.append("This email address is already used by another account.")

        # Phone update is optional, but if one field is filled, both must match.
        if new_phone_number or confirm_phone_number:
            if not new_phone_number:
                errors.append("New phone number is required.")
            if not confirm_phone_number:
                errors.append("Please confirm the new phone number.")
            if new_phone_number and confirm_phone_number and new_phone_number != confirm_phone_number:
                errors.append("New phone number and confirmation phone number do not match.")

        # Address is editable and required.
        if not address_line_1:
            errors.append("Address line 1 is required.")
        if not postcode:
            errors.append("Post code is required.")
        if not country:
            errors.append("Country is required.")

        if errors:
            for error in errors:
                flash(error, "error")
            return redirect(url_for("client_account"))

        now = datetime.now(timezone.utc)

        if new_email:
            user.email = new_email
            client.email = new_email
            session["email"] = new_email

        if new_phone_number:
            client.phone_number = new_phone_number

        client.address_line_1 = address_line_1
        client.address_line_2 = address_line_2
        client.address_line_3 = address_line_3
        client.address_line_4 = address_line_4
        client.postcode = postcode
        client.country = country
        client.updated_at = now

        if hasattr(user, "updated_at"):
            user.updated_at = now

        db.session.commit()

        flash("Account information updated successfully.", "success")
        return redirect(url_for("client_account"))

    return render_template(
        "account.html",
        user=user,
        client=client,
        role="client",
        portal_title="Client Portal",
        page_title="Account Information",
        email=session.get("email"),
        active_page="account",
    )

@app.route("/client/parcel/create", methods=["GET", "POST"])
@role_required("client")
def client_create_parcel():
    user = User.query.get_or_404(session["user_id"])

    if not user.client_id:
        flash("No client account is linked to this user.", "error")
        return redirect(url_for("client_home"))

    parcel_sizes = [
        "Postable parcel or large letter",
        "Standard parcel",
    ]

    delivery_speeds = [
        "Standard",
        "Next Day",
    ]

    if request.method == "POST":
        parcel_size = request.form.get("parcel_size", "").strip()
        delivery_speed = request.form.get("delivery_speed", "").strip()
        parcel_contents = request.form.get("parcel_contents", "").strip()
        parcel_value_gbp = request.form.get("parcel_value_gbp", "").strip()

        recipient_first_name = request.form.get("recipient_first_name", "").strip()
        recipient_last_name = request.form.get("recipient_last_name", "").strip()

        address_line_1 = request.form.get("address_line_1", "").strip()
        address_line_2 = request.form.get("address_line_2", "").strip()
        address_line_3 = request.form.get("address_line_3", "").strip()
        address_line_4 = request.form.get("address_line_4", "").strip()
        postcode = request.form.get("postcode", "").strip()
        country = request.form.get("country", "").strip()

        form_data = {
            "parcel_size": parcel_size,
            "delivery_speed": delivery_speed,
            "parcel_contents": parcel_contents,
            "parcel_value_gbp": parcel_value_gbp,
            "recipient_first_name": recipient_first_name,
            "recipient_last_name": recipient_last_name,
            "address_line_1": address_line_1,
            "address_line_2": address_line_2,
            "address_line_3": address_line_3,
            "address_line_4": address_line_4,
            "postcode": postcode,
            "country": country,
        }

        errors = []

        if parcel_size not in parcel_sizes:
            errors.append("Please select a valid parcel size.")

        if delivery_speed not in delivery_speeds:
            errors.append("Please select a valid delivery speed.")

        required_fields = {
            "parcel_contents": "Parcel contents",
            "parcel_value_gbp": "Parcel value",
            "recipient_first_name": "Recipient first name",
            "recipient_last_name": "Recipient last name",
            "address_line_1": "Address line 1",
            "postcode": "Post code",
            "country": "Country",
        }

        errors.extend(validate_required_fields(form_data, required_fields))

        if len(parcel_contents) > 32:
            errors.append("Parcel contents must be 32 characters or fewer.")

        try:
            parcel_value_float = float(parcel_value_gbp)
            if parcel_value_float < 0:
                errors.append("Parcel value cannot be negative.")
        except ValueError:
            errors.append("Parcel value must be a valid number.")

        if errors:
            for error in errors:
                flash(error, "error")

            return render_template(
                "create_parcel.html",
                role="client",
                portal_title="Client Portal",
                page_title="Create Parcel",
                email=session.get("email"),
                active_page="create_label",
                parcel_sizes=parcel_sizes,
                delivery_speeds=delivery_speeds,
                form_data=form_data,
            )

        now = datetime.now(timezone.utc)

        tracking_number = generate_tracking_number()

        while Parcel.query.filter_by(tracking_number=tracking_number).first():
            tracking_number = generate_tracking_number()

        parcel = Parcel(
            tracking_number=tracking_number,
            client_id=user.client_id,
            created_by_user_id=user.id,
            parcel_size=parcel_size,
            delivery_speed=delivery_speed,
            parcel_contents=parcel_contents,
            parcel_value_gbp=parcel_value_float,
            recipient_first_name=recipient_first_name,
            recipient_last_name=recipient_last_name,
            recipient_address_line_1=address_line_1,
            recipient_address_line_2=address_line_2,
            recipient_address_line_3=address_line_3,
            recipient_address_line_4=address_line_4,
            recipient_postcode=postcode,
            recipient_country=country,
            status="Label Generated",
            created_at=now,
            updated_at=now,
        )

        db.session.add(parcel)
        db.session.flush()

        create_initial_track_event(parcel)

        db.session.commit()

        flash(f"Parcel {tracking_number} has been created successfully.", "success")
        return redirect(url_for("client_create_parcel"))

    return render_template(
        "create_parcel.html",
        role="client",
        portal_title="Client Portal",
        page_title="Create Parcel",
        email=session.get("email"),
        active_page="create_label",
        parcel_sizes=parcel_sizes,
        delivery_speeds=delivery_speeds,
        form_data={},
    )

@app.route("/client/parcel")
@role_required("client")
def client_parcels():
    user = User.query.get_or_404(session["user_id"])

    if not user.client_id:
        flash("No client account is linked to this user.", "error")
        return redirect(url_for("client_home"))

    search_by = request.args.get("search_by", "tracking_number")
    search_value = request.args.get("search_value", "").strip()

    # SECURITY: client_id filter is always applied first.
    # This ensures clients can only ever see their own parcels,
    # even if they search for another client's tracking number.
    query = Parcel.query.filter(Parcel.client_id == user.client_id)

    if search_value:
        if search_by == "tracking_number":
            query = query.filter(Parcel.tracking_number.ilike(f"%{search_value}%"))

        elif search_by == "recipient_name":
            query = query.filter(
                db.or_(
                    Parcel.recipient_first_name.ilike(f"%{search_value}%"),
                    Parcel.recipient_last_name.ilike(f"%{search_value}%")
                )
            )

        elif search_by == "recipient_postcode":
            query = query.filter(Parcel.recipient_postcode.ilike(f"%{search_value}%"))

        else:
            # Invalid search option should not expose anything unexpected.
            query = query.filter(Parcel.id == -1)

    parcels = query.order_by(Parcel.created_at.desc()).all()

    return render_template(
        "parcels.html",
        parcels=parcels,
        role="client",
        portal_title="Client Portal",
        page_title="Your parcels",
        email=session.get("email"),
        active_page="parcels",
        search_by=search_by,
        search_value=search_value,
    )


@app.route("/admin/parcel")
@role_required("admin")
def admin_parcels():
    search_by = request.args.get("search_by", "tracking_number")
    search_value = request.args.get("search_value", "").strip()

    query = Parcel.query

    if search_value:
        if search_by == "tracking_number":
            query = query.filter(Parcel.tracking_number.ilike(f"%{search_value}%"))

        elif search_by == "recipient_name":
            query = query.filter(
                db.or_(
                    Parcel.recipient_first_name.ilike(f"%{search_value}%"),
                    Parcel.recipient_last_name.ilike(f"%{search_value}%")
                )
            )

        elif search_by == "recipient_postcode":
            query = query.filter(Parcel.recipient_postcode.ilike(f"%{search_value}%"))

        elif search_by == "client_name":
            query = query.join(Client).filter(Client.client_name.ilike(f"%{search_value}%"))

    parcels = query.order_by(Parcel.created_at.desc()).all()

    return render_template(
        "parcels.html",
        parcels=parcels,
        role="admin",
        portal_title="Admin Portal",
        page_title="Parcels",
        email=session.get("email"),
        active_page="parcels",
        search_by=search_by,
        search_value=search_value,
    )

@app.route("/client/parcel/<int:parcel_id>")
@role_required("client")
def client_view_parcel(parcel_id):
    user = User.query.get_or_404(session["user_id"])

    parcel = Parcel.query.get_or_404(parcel_id)

    if parcel.client_id != user.client_id:
        flash("You do not have permission to view that parcel.", "error")
        return redirect(url_for("client_parcels"))

    track_events = (
        TrackEvent.query
        .filter_by(parcel_id=parcel.id, visible_to_client=True)
        .order_by(TrackEvent.created_at.desc())
        .all()
    )

    return render_template(
        "view_parcel.html",
        parcel=parcel,
        track_events=track_events,
        tracking_statuses=[],
        role="client",
        portal_title="Client Portal",
        page_title="View Parcel",
        email=session.get("email"),
        active_page="parcels",
    )


@app.route("/admin/parcel/<int:parcel_id>", methods=["GET", "POST"])
@role_required("admin")
def admin_view_parcel(parcel_id):
    parcel = Parcel.query.get_or_404(parcel_id)

    tracking_statuses = [
        "In Transit",
        "Out for Delivery",
        "Delivered",
        "Delayed",
        "Stop and return",
        "Cancelled",
    ]

    if request.method == "POST":
        event_status = request.form.get("event_status", "").strip()
        event_location = request.form.get("event_location", "").strip()
        event_description = request.form.get("event_description", "").strip()
        visible_to_client = request.form.get("visible_to_client") == "yes"

        errors = []

        if event_status not in tracking_statuses:
            errors.append("Please select a valid tracking status.")

        if not event_location:
            errors.append("Event location is required.")

        if not event_description:
            errors.append("Event description is required.")

        if errors:
            for error in errors:
                flash(error, "error")

            return redirect(url_for("admin_view_parcel", parcel_id=parcel.id))

        now = datetime.now(timezone.utc)

        track_event = TrackEvent(
            parcel_id=parcel.id,
            event_status=event_status,
            event_location=event_location,
            event_description=event_description,
            visible_to_client=visible_to_client,
            created_at=now,
        )

        parcel.status = event_status
        parcel.updated_at = now

        db.session.add(track_event)
        db.session.commit()

        flash("Tracking event added successfully.", "success")
        return redirect(url_for("admin_view_parcel", parcel_id=parcel.id))

    track_events = (
        TrackEvent.query
        .filter_by(parcel_id=parcel.id)
        .order_by(TrackEvent.created_at.desc())
        .all()
    )

    return render_template(
        "view_parcel.html",
        parcel=parcel,
        track_events=track_events,
        tracking_statuses=tracking_statuses,
        role="admin",
        portal_title="Admin Portal",
        page_title="View Parcel",
        email=session.get("email"),
        active_page="parcels",
    )

@app.route("/admin/client/<int:client_id>", methods=["GET", "POST"])
@role_required("admin")
def admin_view_client(client_id):
    client = Client.query.get_or_404(client_id)

    linked_users = User.query.filter_by(client_id=client.id, role="client").all()
    primary_user = linked_users[0] if linked_users else None

    if request.method == "POST":

        client_name = request.form.get("client_name", "").strip()
        short_name = request.form.get("short_name", "").strip().upper()
        status = request.form.get("status", "").strip()
        account_manager = request.form.get("account_manager", "").strip()

        allow_stop_and_return = request.form.get("allow_stop_and_return") == "yes"
        must_reset_password = request.form.get("must_reset_password") == "yes"

        new_email = request.form.get("new_email", "").strip().lower()
        confirm_email = request.form.get("confirm_email", "").strip().lower()

        new_phone_number = request.form.get("new_phone_number", "").strip()
        confirm_phone_number = request.form.get("confirm_phone_number", "").strip()

        address_line_1 = request.form.get("address_line_1", "").strip()
        address_line_2 = request.form.get("address_line_2", "").strip()
        address_line_3 = request.form.get("address_line_3", "").strip()
        address_line_4 = request.form.get("address_line_4", "").strip()
        postcode = request.form.get("postcode", "").strip()
        country = request.form.get("country", "").strip()

        errors = []

        if not client_name:
            errors.append("Client name is required.")

        if not short_name:
            errors.append("Short name is required.")

        if status not in ["Active", "Inactive", "Pending"]:
            errors.append("Please select a valid client status.")

        if not account_manager:
            errors.append("Account manager is required.")

        if not address_line_1:
            errors.append("Address line 1 is required.")

        if not postcode:
            errors.append("Post code is required.")

        if not country:
            errors.append("Country is required.")

        existing_client_name = Client.query.filter(
            db.func.lower(Client.client_name) == client_name.lower(),
            Client.id != client.id
        ).first()

        if existing_client_name:
            errors.append("Another client already exists with this client name.")

        existing_short_name = Client.query.filter(
            db.func.lower(Client.short_name) == short_name.lower(),
            Client.id != client.id
        ).first()

        if existing_short_name:
            errors.append("Another client already exists with this short name.")

        if new_email or confirm_email:
            if not new_email:
                errors.append("New email address is required.")
            if not confirm_email:
                errors.append("Please confirm the new email address.")
            if new_email and confirm_email and new_email != confirm_email:
                errors.append("New email address and confirmation email do not match.")

            existing_user = User.query.filter(
                User.email == new_email,
                User.id != primary_user.id if primary_user else True
            ).first()

            if existing_user:
                errors.append("This email address is already used by another user account.")

        if new_phone_number or confirm_phone_number:
            if not new_phone_number:
                errors.append("New phone number is required.")
            if not confirm_phone_number:
                errors.append("Please confirm the new phone number.")
            if new_phone_number and confirm_phone_number and new_phone_number != confirm_phone_number:
                errors.append("New phone number and confirmation phone number do not match.")

        if errors:
            for error in errors:
                flash(error, "error")
            return redirect(url_for("admin_view_client", client_id=client.id))

        now = datetime.now(timezone.utc)

        client.client_name = client_name
        client.short_name = short_name
        client.status = status
        client.account_manager = account_manager
        client.allow_stop_and_return = allow_stop_and_return

        if new_email:
            client.email = new_email
            if primary_user:
                primary_user.email = new_email

        if new_phone_number:
            client.phone_number = new_phone_number

        client.address_line_1 = address_line_1
        client.address_line_2 = address_line_2
        client.address_line_3 = address_line_3
        client.address_line_4 = address_line_4
        client.postcode = postcode
        client.country = country
        client.updated_at = now

        for linked_user in linked_users:
            linked_user.display_name = client_name
            linked_user.must_reset_password = must_reset_password
            if hasattr(linked_user, "updated_at"):
                linked_user.updated_at = now

        db.session.commit()

        flash("Client updated successfully.", "success")
        return redirect(url_for("admin_view_client", client_id=client.id))

    return render_template(
        "view_client.html",
        client=client,
        primary_user=primary_user,
        role="admin",
        portal_title="Admin Portal",
        page_title="View Client",
        email=session.get("email"),
        active_page="clients",
    )

@app.route("/logout")
@login_required
def logout():
    session.clear()
    flash("Successfully logged out.", "success")
    return render_template("logout.html")


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    with app.app_context():
        create_database_and_seed_users()

    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)), debug=True)