import secrets
import string
from datetime import datetime, timezone
from werkzeug.security import generate_password_hash
from urllib.parse import quote
from flask import flash, session, redirect, url_for

from extensions import db
from models import Enquiry, EnquiryComment, TrackEvent, Client, User, Parcel

def generate_temporary_password(length=14):
    """
    Generates a temporary password for newly created client accounts.
    This is shown once to the admin and only the hash is stored.
    """

    characters = string.ascii_letters + string.digits + "!@#$%&*"
    return "".join(secrets.choice(characters) for _ in range(length))

def generate_tracking_number():
    """
    Generates a prototype tracking number.
    In a real system, this would likely come from a dedicated parcel/label service.
    """

    random_part = "".join(secrets.choice(string.digits) for _ in range(15))
    return f"H{random_part}"

def add_system_comment(enquiry_id, comment_text):
    """
    Adds a system comment to an enquiry, for example when the enquiry is created or updated.
    """

    system_comment = EnquiryComment(
        enquiry_id=enquiry_id,
        user_id=1,
        comment=comment_text,
        created_at=datetime.now(timezone.utc),
    )
    db.session.add(system_comment)

def format_enquiry_number(enquiry_id):
    return f"ENQ{enquiry_id:06d}"

def build_enquiry_change_comment(old, new, actor_display_name=None):
    """
    Build a human-readable change summary comparing old and new enquiry values.

    `old` and `new` can be either objects (with attributes) or dictionaries.
    Returns a single string ready to be saved as a system comment, or None if
    there are no changes.
    """
    def _get(source, key):
        if source is None:
            return None
        if isinstance(source, dict):
            return source.get(key)
        return getattr(source, key, None)

    fields = [
        ("category", "Category"),
        ("tracking_number", "Tracking number"),
        ("subject", "Subject"),
        ("message", "Message"),
        ("status", "Status"),
    ]

    changes = []

    for key, label in fields:
        old_val = _get(old, key)
        new_val = _get(new, key)

        # Normalize None/empty for nicer display
        old_display = old_val if old_val is not None else ""
        new_display = new_val if new_val is not None else ""

        if str(old_display) != str(new_display):
            if old_display == "":
                old_display = "(none)"
            if new_display == "":
                new_display = "(none)"
            changes.append(f"{label}: {old_display} -> {new_display}")

    if not changes:
        return None

    actor = actor_display_name or "A user"
    return f"{actor} updated the enquiry: " + "; ".join(changes)

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

def handle_step_errors(errors, data, step):
    """
    Flash errors and save session data, then redirect back to the current step.
    Returns a redirect response if errors exist, None otherwise.
    """

    if errors:
        for error in errors:
            flash(error, "error")
        save_new_client_session_data(data)
        return redirect(url_for("admin.admin_create_client", step=step))
    
    return None

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

def update_user(user, *, email=None, password=None, role=None, display_name=None, client_id=None, must_reset_password=None, is_active=None):
    """
    Updates a user record using optional keyword arguments.

    Only values passed into the function are updated.
    The * forces arguments to be passed by name, preventing mistakes caused
    by incorrect argument order.
    """

    if email is not None:
        user.email = email

    if password is not None:
        user.password_hash = generate_password_hash(password)

    if role is not None:
        user.role = role

    if display_name is not None:
        user.display_name = display_name

    if client_id is not None:
        user.client_id = client_id

    if must_reset_password is not None:
        user.must_reset_password = must_reset_password

    if is_active is not None:
        user.is_active = is_active

    user.updated_at = datetime.now(timezone.utc)

def update_client(client, *, client_name=None, short_name=None, status=None, account_manager=None, phone_number=None, email=None, address_line_1=None, address_line_2=None, address_line_3=None, address_line_4=None, postcode=None, country=None, allow_stop_and_return=None):
    """
    Updates a client record using optional keyword arguments.

    Only values passed into the function are updated.
    The * forces arguments to be passed by name, which prevents mistakes
    caused by incorrect argument order.
    """

    if client_name is not None:
        client.client_name = client_name

    if short_name is not None:
        client.short_name = short_name

    if status is not None:
        client.status = status

    if account_manager is not None:
        client.account_manager = account_manager

    if phone_number is not None:
        client.phone_number = phone_number

    if email is not None:
        client.email = email

    if address_line_1 is not None:
        client.address_line_1 = address_line_1

    if address_line_2 is not None:
        client.address_line_2 = address_line_2

    if address_line_3 is not None:
        client.address_line_3 = address_line_3

    if address_line_4 is not None:
        client.address_line_4 = address_line_4

    if postcode is not None:
        client.postcode = postcode

    if country is not None:
        client.country = country

    if allow_stop_and_return is not None:
        client.allow_stop_and_return = allow_stop_and_return

    client.updated_at = datetime.now(timezone.utc)

def create_client_object(form_data):
    """
    Creates a new Client object from form data.
    """

    now = datetime.now(timezone.utc)

    return Client(
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

def create_client_user_object(form_data, hashed_password, id):
    return User(
                email=form_data["email"],
                password_hash=hashed_password,
                role="client",
                display_name=form_data["client_name"],
                client_id=id,
                must_reset_password=True,
                is_active=True,
            )

def create_enquiry_object(admin_id, category, subject, message, tracking_number=None):
    now = datetime.now(timezone.utc)

    return Enquiry(
            created_by_user_id=admin_id,
            category=category,
            subject=subject,
            message=message,
            tracking_number=tracking_number if tracking_number else None,
            status="New",
            created_at=now,
            updated_at=now,
        )

def update_enquiry(enquiry, *, category=None, subject=None, message=None, status=None, tracking_number=None, closed_at=None):
    if category is not None:
        enquiry.category = category

    if subject is not None:
        enquiry.subject = subject

    if message is not None:
        enquiry.message = message

    if status is not None:
        enquiry.status = status

    if tracking_number is not None:
        enquiry.tracking_number = tracking_number

    if closed_at is not None:
        enquiry.closed_at = closed_at

    enquiry.updated_at = datetime.now(timezone.utc)

def create_enquiry_comment_object(enquiry_id, user_id, comment):
    now = datetime.now(timezone.utc)

    return EnquiryComment(
            enquiry_id=enquiry_id,
            user_id=user_id,
            comment=comment,
            created_at=now,
        )

def create_parcel_object(tracking_number, client_id, user_id, form_data):
    now = datetime.now(timezone.utc)

    return Parcel(
            tracking_number=tracking_number,
            client_id=client_id,
            created_by_user_id=user_id,
            parcel_size=form_data["parcel_size"],
            delivery_speed=form_data["delivery_speed"],
            parcel_contents=form_data["parcel_contents"],
            parcel_value_gbp=form_data["parcel_value_gbp"],
            recipient_first_name=form_data["recipient_first_name"],
            recipient_last_name=form_data["recipient_last_name"],
            recipient_address_line_1=form_data["address_line_1"],
            recipient_address_line_2=form_data["address_line_2"],
            recipient_address_line_3=form_data["address_line_3"],
            recipient_address_line_4=form_data["address_line_4"],
            recipient_postcode=form_data["postcode"],
            recipient_country=form_data["country"],
            status="Label Generated",
            created_at=now,
            updated_at=now,
        )
