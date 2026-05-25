from flask import Blueprint, render_template, request, redirect, url_for, session, flash
from werkzeug.security import generate_password_hash

from auth_utils import role_required
from extensions import db
from models import User, Client
from helpers import build_client_onboarding_mailto, create_client_user_object, get_new_client_session_data, handle_step_errors, save_new_client_session_data, generate_temporary_password, create_client_object, update_client, update_user
from validators import is_client_name_taken, is_client_short_name_taken, validate, is_email_taken, validate_new_email, validate_new_phone_number

admin_bp = Blueprint("admin", __name__)

@admin_bp.route("/admin/home")
@role_required("admin")
def admin_home():
    return render_template(
        "home.html",
        portal_title="Admin Portal",
        display_name=session.get("display_name"),
        email=session.get("email"),
        role="admin",
    )


@admin_bp.route("/admin/clients")
@role_required("admin")
def admin_clients():
    """
    Displays the list of clients, with optional search and filtering.
    """
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


@admin_bp.route("/admin/client/create", methods=["GET", "POST"])
@role_required("admin")
def admin_create_client():
    """
    Multi-step form to create a new client and associated primary user account.
    """

    # Validate step parameter and default to step 1 if invalid
    step = request.args.get("step", "1")

    if not step.isdigit():
        step = 1
    else:
        step = int(step)

    if step < 1 or step > 5:
        step = 1



    # Prevent direct access to later steps if required previous data is missing
    form_data = get_new_client_session_data()

    if step == 2 and not form_data.get("client_name"):
        flash("Please complete client details first.", "error")
        return redirect(url_for("admin.admin_create_client", step=1))

    if step == 3 and not form_data.get("address_line_1"):
        flash("Please complete the business address first.", "error")
        return redirect(url_for("admin.admin_create_client", step=2))

    if step == 4 and not form_data.get("short_name"):
        flash("Please complete client settings first.", "error")
        return redirect(url_for("admin.admin_create_client", step=3))

    if step == 5:
        created_client_id = session.get("created_client_id")
        temporary_password = session.get("created_client_temp_password")

        if not created_client_id or not temporary_password:
            flash("Please create a client first.", "error")
            return redirect(url_for("admin.admin_create_client", step=1))

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


    # Handle form submission for each step
    if request.method == "POST":
        # Step 1: Client Details
        if step == 1:
            data = {
                "client_name": request.form.get("client_name", "").strip(),
                "phone_number": request.form.get("phone_number", "").strip(),
                "email": request.form.get("email", "").strip().lower(),
            }

            # Validate inputs using validators.py functions. We also check that the new email and phone number match their confirmation fields.
            errors = []

            errors.extend(is_email_taken(data["email"]))
            errors.extend(is_client_name_taken(data["client_name"]))
            errors.extend(validate(data["client_name"], "Client name", ["required", "max_length:120"]))
            errors.extend(validate(data["phone_number"], "Phone number", ["required", "max_length:31"]))
            errors.extend(validate(data["email"], "Email address", ["required", "email", "max_length:120"]))

            # In each step:
            result = handle_step_errors(errors, data, step)
            if result:  # If errors exist, return the redirect response
                return result
            
            # If NO errors, continue with the next step
            save_new_client_session_data(data)
            return redirect(url_for("admin.admin_create_client", step=2))



        # Step 2: Business Address
        if step == 2:
            data = {
                "address_line_1": request.form.get("address_line_1", "").strip(),
                "address_line_2": request.form.get("address_line_2", "").strip(),
                "address_line_3": request.form.get("address_line_3", "").strip(),
                "address_line_4": request.form.get("address_line_4", "").strip(),
                "postcode": request.form.get("postcode", "").strip(),
                "country": request.form.get("country", "").strip()
            }

            # Validate inputs using validators.py functions.
            errors = []

            errors.extend(validate(data["address_line_1"], "Address line 1", ["required", "max_length:120"]))
            errors.extend(validate(data["address_line_2"], "Address line 2", ["max_length:120"]))
            errors.extend(validate(data["address_line_3"], "Address line 3", ["max_length:120"]))
            errors.extend(validate(data["address_line_4"], "Address line 4", ["max_length:120"]))
            errors.extend(validate(data["postcode"], "Post code", ["required", "max_length:20"]))
            errors.extend(validate(data["country"], "Country", ["required", "max_length:80"]))

            # In each step:
            result = handle_step_errors(errors, data, step)
            if result:  # If errors exist, return the redirect response
                return result
            
            # If NO errors, continue with the next step
            save_new_client_session_data(data)
            return redirect(url_for("admin.admin_create_client", step=3))

        # Step 3: Settings
        if step == 3:
            data = {
                "short_name": request.form.get("short_name", "").strip().upper(),
                "status": request.form.get("status", "").strip(),
                "allow_stop_and_return": request.form.get("allow_stop_and_return") == "yes"
            }

            errors = []

            errors.extend(validate(data["short_name"], "Short name", ["required", "min_length:3", "max_length:4"]))
            errors.extend(validate(data["status"], "Status", ["required", "client_status"]))
            errors.extend(is_client_short_name_taken(data["short_name"]))

            # In each step:
            result = handle_step_errors(errors, data, step)
            if result:  # If errors exist, return the redirect response
                return result

            # If NO errors, continue with the next step
            save_new_client_session_data(data)
            return redirect(url_for("admin.admin_create_client", step=4))

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
            
            errors = []

             # Validate required fields
            for field_key, field_name in required_before_create.items():
                errors.extend(validate(form_data.get(field_key), field_name, ["required"]))
            
            if errors:
                for error in errors:
                    flash(error, "error")
                return redirect(url_for("admin.admin_create_client", step=1))

            if is_email_taken(form_data["email"]):
                flash("A user account already exists with this email address.", "error")
                return redirect(url_for("admin.admin_create_client", step=1))
            
            if is_client_name_taken(form_data["client_name"]):
                flash("A client already exists with this client name.", "error")
                return redirect(url_for("admin.admin_create_client", step=1))

            if is_client_short_name_taken(form_data["short_name"]):
                flash("A client already exists with this short name.", "error")
                return redirect(url_for("admin.admin_create_client", step=3))

            new_client = create_client_object(form_data)

            db.session.add(new_client)
            db.session.flush()  # Gives us new_client.id before commit

            temporary_password = generate_temporary_password()


            new_client_user = create_client_user_object(form_data, generate_password_hash(temporary_password), new_client.id)

            db.session.add(new_client_user)
            db.session.commit()

            session["created_client_id"] = new_client.id
            session["created_client_temp_password"] = temporary_password

            # Clear the draft form data now that the client is created
            session.pop("new_client", None)
            session.modified = True

            flash("Successfully created the client.", "success")
            return redirect(url_for("admin.admin_create_client", step=5))

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


@admin_bp.route("/admin/client/<int:client_id>", methods=["GET", "POST"])
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

        errors.extend(validate(client_name, "Client name", ["required", "max_length:120"]))
        errors.extend(validate(short_name, "Short name", ["required", "min_length:3", "max_length:4"]))
        errors.extend(validate(status, "Status", ["required", "client_status"]))
        errors.extend(validate(account_manager, "Account manager", ["required", "max_length:100"]))
        errors.extend(validate(address_line_1, "Address line 1", ["required", "max_length:120"]))
        errors.extend(validate(address_line_2, "Address line 2", ["max_length:120"]))
        errors.extend(validate(address_line_3, "Address line 3", ["max_length:120"]))
        errors.extend(validate(address_line_4, "Address line 4", ["max_length:120"]))
        errors.extend(validate(postcode, "Post code", ["required", "max_length:20"]))
        errors.extend(validate(country, "Country", ["required", "max_length:80"]))
        errors.extend(validate_new_email(new_email, confirm_email, primary_user))
        errors.extend(validate_new_phone_number(new_phone_number, confirm_phone_number))
        errors.extend(is_client_name_taken(client_name, client.id))
        errors.extend(is_client_short_name_taken(short_name, client.id))

        if errors:
            for error in errors:
                flash(error, "error")
            return redirect(url_for("admin.admin_view_client", client_id=client.id))

        update_client(
            client,
            client_name=client_name,
            short_name=short_name,
            status=status,
            account_manager=account_manager,
            address_line_1=address_line_1,
            address_line_2=address_line_2,
            address_line_3=address_line_3,
            address_line_4=address_line_4,
            postcode=postcode,
            country=country,
            allow_stop_and_return=allow_stop_and_return
        )

        if new_email:
            update_client(client, email=new_email)
            if primary_user:
                update_user(primary_user, email=new_email)

        if status != "Active":
            for linked_user in linked_users:
                update_user(linked_user, is_active=False)
        else:            
            for linked_user in linked_users:
                update_user(linked_user, is_active=True)

        if new_phone_number:
            update_client(client, phone_number=new_phone_number)

        for linked_user in linked_users:
            update_user(linked_user, must_reset_password=must_reset_password, display_name=client_name)

        db.session.commit()

        flash("Client updated successfully.", "success")
        return redirect(url_for("admin.admin_view_client", client_id=client.id))

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


@admin_bp.route("/admin/account", methods=["GET", "POST"])
@role_required("admin")
def admin_account():
    user = User.query.get_or_404(session["user_id"])

    if request.method == "POST":
        new_email = request.form.get("new_email", "").strip().lower()
        confirm_email = request.form.get("confirm_email", "").strip().lower()

        errors = []
        
        errors.extend(validate_new_email(new_email, confirm_email, user))

        if errors:
            for error in errors:
                flash(error, "error")

            return redirect(url_for("admin.admin_account"))

        update_user(user, email=new_email)

        db.session.commit()

        session["email"] = user.email

        flash("Account email address updated successfully.", "success")
        return redirect(url_for("admin.admin_account"))

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