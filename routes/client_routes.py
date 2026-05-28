from flask import Blueprint, render_template, request, redirect, url_for, session, flash, current_app

from auth_utils import role_required
from extensions import db, limiter
from models import User, Client
from helpers import update_client, update_user
from validators import validate, validate_new_email, validate_new_phone_number

client_bp = Blueprint("client", __name__)

@client_bp.route("/client/home")
@role_required("client")
def client_home():
    return render_template(
        "home.html",
        portal_title="Client Portal",
        display_name=session.get("display_name"),
        email=session.get("email"),
        role="client",
    )


@client_bp.route("/client/account", methods=["GET", "POST"])
@limiter.limit("5 per minute", methods=["POST"])
@role_required("client")
def client_account():
    """
    Allows clients to view and update their account information, including email, phone number, and address.
    """
    
    # Get the logged-in user from the database using their user_id from the session. We use get_or_404 to handle the case where the user_id is invalid, which should not happen under normal circumstances since the user must be logged in to access this route.
    user = User.query.get_or_404(session["user_id"]) 

    # This should not happen under normal circumstances, but we check just in case
    if not user.client_id:
        flash("No client account is linked to this user.", "error")
        return redirect(url_for("client.client_home"))

    # We can safely query the client using the user's client_id, since we know it exists. This also ensures that clients can only access their own account information.
    client = Client.query.get_or_404(user.client_id)
    
    # Handle account update form submission
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

        # Validate inputs using validators.py functions. We also check that the new email and phone number match their confirmation fields.
        errors = []

        errors.extend(validate_new_email(new_email, confirm_email, user))
        errors.extend(validate_new_phone_number(new_phone_number, confirm_phone_number))
        errors.extend(validate(new_email, "New email", ["email", "max_length:120"]))
        errors.extend(validate(new_phone_number, "New phone number", ["max_length:31"]))
        errors.extend(validate(address_line_1, "Address line 1", ["required", "max_length:120"]))
        errors.extend(validate(address_line_2, "Address line 2", ["max_length:120"]))
        errors.extend(validate(address_line_3, "Address line 3", ["max_length:120"]))
        errors.extend(validate(address_line_4, "Address line 4", ["max_length:120"]))
        errors.extend(validate(postcode, "Post code", ["required", "max_length:20"]))
        errors.extend(validate(country, "Country", ["required", "max_length:80"]))

        # If there are validation errors, flash them and redirect back to the account page
        if errors:
            for error in errors:
                flash(error, "error")
            return redirect(url_for("client.client_account"))

        current_app.logger.info(
            "Client User (ID: %s) is updating client (ID: %s) information.",
            user.id,
            client.id,
        )
         # Update the client record with the new information. Only fields that have been filled out will be updated, thanks to the use of optional keyword arguments in the update_client function.
        update_client(
            client,address_line_1=address_line_1,
            address_line_2=address_line_2,
            address_line_3=address_line_3,
            address_line_4=address_line_4,
            postcode=postcode,
            country=country
        )

        # If the email is being updated, we also need to update the user's email and the session email, since the email is used for login and displayed in the portal. We use the update_user helper function to update the user's email, which also updates the updated_at timestamp.
        if new_email:
            update_user(user, email=new_email)
            update_client(client, email=new_email)
            session["email"] = new_email

        # If the phone number is being updated, we update it in the client record. We don't need to update the user record since the phone number is not stored there.
        if new_phone_number:
            update_client(client, phone_number=new_phone_number)

        db.session.commit()

        flash("Account information updated successfully.", "success")
        return redirect(url_for("client.client_account"))

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