from flask import Blueprint, render_template, request, redirect, url_for, session, flash, current_app
from datetime import datetime, timezone

from auth_utils import login_required, role_required
from extensions import db, limiter
from models import User, Client, Parcel, TrackEvent
from config import PARCEL_SIZES, DELIVERY_SPEEDS
from helpers import can_user_stop_and_return, create_parcel_object, generate_tracking_number, create_initial_track_event
from validators import validate
parcel_bp = Blueprint("parcel", __name__)

@parcel_bp.route("/client/parcel/create", methods=["GET", "POST"])
@limiter.limit("20 per minute", methods=["POST"])
@role_required("client")
def client_create_parcel():
    user = User.query.get_or_404(session["user_id"])

    if not user.client_id:
        flash("No client account is linked to this user.", "error")
        return redirect(url_for("client.client_home"))

    if request.method == "POST":
        form_data = {
            "parcel_size": request.form.get("parcel_size", "").strip(),
            "delivery_speed": request.form.get("delivery_speed", "").strip(),
            "parcel_contents": request.form.get("parcel_contents", "").strip(),
            "parcel_value_gbp": request.form.get("parcel_value_gbp", "").strip(),
            "recipient_first_name": request.form.get("recipient_first_name", "").strip(),
            "recipient_last_name": request.form.get("recipient_last_name", "").strip(),
            "address_line_1": request.form.get("address_line_1", "").strip(),
            "address_line_2": request.form.get("address_line_2", "").strip(),
            "address_line_3": request.form.get("address_line_3", "").strip(),
            "address_line_4": request.form.get("address_line_4", "").strip(),
            "postcode": request.form.get("postcode", "").strip(),
            "country": request.form.get("country", "").strip(),
        }

        errors = []

        if form_data["parcel_size"] not in PARCEL_SIZES:
            errors.append("Please select a valid parcel size.")

        if form_data["delivery_speed"] not in DELIVERY_SPEEDS:
            errors.append("Please select a valid delivery speed.")
            
        errors.extend(validate(form_data["parcel_contents"], "Parcel contents", ["required", "max_length:32"]))
        errors.extend(validate(form_data["parcel_value_gbp"], "Parcel value", ["required", "gbp", "min_value:0", "max_value:10000"]))
        errors.extend(validate(form_data["recipient_first_name"], "Recipient first name", ["required", "max_length:50"]))
        errors.extend(validate(form_data["recipient_last_name"], "Recipient last name", ["required", "max_length:50"]))
        errors.extend(validate(form_data["address_line_1"], "Address line 1", ["required", "max_length:120"]))
        errors.extend(validate(form_data["address_line_2"], "Address line 2", ["max_length:120"]))
        errors.extend(validate(form_data["address_line_3"], "Address line 3", ["max_length:120"]))
        errors.extend(validate(form_data["address_line_4"], "Address line 4", ["max_length:120"]))
        errors.extend(validate(form_data["postcode"], "Post code", ["required", "max_length:20"]))
        errors.extend(validate(form_data["country"], "Country", ["required", "max_length:80"]))


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
                parcel_sizes=PARCEL_SIZES,
                delivery_speeds=DELIVERY_SPEEDS,
                form_data=form_data,
            )

        now = datetime.now(timezone.utc)

        tracking_number = generate_tracking_number()

        while Parcel.query.filter_by(tracking_number=tracking_number).first():
            tracking_number = generate_tracking_number()

        parcel = create_parcel_object(tracking_number, user.client_id, user.id, form_data)

        db.session.add(parcel)
        db.session.flush()

        create_initial_track_event(parcel)

        db.session.commit()

        current_app.logger.info(
            "Client user (ID: %s) created parcel (ID: %s, Tracking number: %s).",
            user.id,
            parcel.id,
            parcel.tracking_number,
        )

        flash(f"Parcel {tracking_number} has been created successfully.", "success")
        return redirect(url_for("parcel.client_create_parcel"))

    return render_template(
        "create_parcel.html",
        role="client",
        portal_title="Client Portal",
        page_title="Create Parcel",
        email=session.get("email"),
        active_page="create_label",
        parcel_sizes=PARCEL_SIZES,
        delivery_speeds=DELIVERY_SPEEDS,
        form_data={},
    )

@parcel_bp.route("/client/parcel")
@role_required("client")
def client_parcels():
    user = User.query.get_or_404(session["user_id"])

    if not user.client_id:
        flash("No client account is linked to this user.", "error")
        return redirect(url_for("client.client_home"))

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


@parcel_bp.route("/admin/parcel")
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

@parcel_bp.route("/client/parcel/<int:parcel_id>")
@role_required("client")
def client_view_parcel(parcel_id):
    parcel = Parcel.query.get_or_404(parcel_id)
    
    user = User.query.get_or_404(session["user_id"])
    can_stop_return, stop_return_reason = can_user_stop_and_return(parcel, user)

    if parcel.client_id != user.client_id:
        flash("You do not have permission to view that parcel.", "error")
        return redirect(url_for("parcel.client_parcels"))

    track_events = (
        TrackEvent.query
        .filter_by(parcel_id=parcel.id, visible_to_client=True)
        .order_by(TrackEvent.created_at.desc(), TrackEvent.id.desc())
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
        can_stop_return=can_stop_return,
        stop_return_reason=stop_return_reason
    )


@parcel_bp.route("/admin/parcel/<int:parcel_id>", methods=["GET", "POST"])
@limiter.limit("20 per minute", methods=["POST"])
@role_required("admin")
def admin_view_parcel(parcel_id):
    parcel = Parcel.query.get_or_404(parcel_id)

    user = User.query.get_or_404(session["user_id"])
    can_stop_return, stop_return_reason = can_user_stop_and_return(parcel, user)

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

            return redirect(url_for("parcel.admin_view_parcel", parcel_id=parcel.id))

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

        current_app.logger.info(
            "Admin user (ID: %s) added tracking event (ID: %s, Status: %s) for parcel (ID: %s).",
            session["user_id"],
            track_event.id,
            track_event.event_status,
            parcel.id
        )

        flash("Tracking event added successfully.", "success")
        return redirect(url_for("parcel.admin_view_parcel", parcel_id=parcel.id))

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
        can_stop_return=can_stop_return,
        stop_return_reason=stop_return_reason
    )

@parcel_bp.route("/parcel/<int:parcel_id>/stop-return", methods=["POST"])
@limiter.limit("20 per minute", methods=["POST"])
@login_required
def stop_and_return_parcel(parcel_id):
    user = User.query.get_or_404(session["user_id"])
    parcel = Parcel.query.get_or_404(parcel_id)

    allowed, message = can_user_stop_and_return(parcel, user)

    if not allowed:
        flash(message, "error")

        if user.role == "admin":
            return redirect(url_for("parcel.admin_view_parcel", parcel_id=parcel.id))

        return redirect(url_for("parcel.client_view_parcel", parcel_id=parcel.id))

    now = datetime.now(timezone.utc)

    stop_return_event = TrackEvent(
        parcel_id=parcel.id,
        event_status="Stop and return",
        event_location="Client Portal" if user.role == "client" else "Admin Portal",
        event_description="A Stop and Return request has been applied to this parcel.",
        visible_to_client=True,
        created_at=now,
    )

    parcel.status = "Stop and return"
    parcel.updated_at = now

    db.session.add(stop_return_event)
    db.session.commit()

    current_app.logger.info(
        "User (ID: %s) applied Stop and Return to parcel (ID: %s).",
        session["user_id"],
        parcel.id
    )

    flash("Stop and Return has been applied to this parcel.", "success")

    if user.role == "admin":
        return redirect(url_for("parcel.admin_view_parcel", parcel_id=parcel.id))

    return redirect(url_for("parcel.client_view_parcel", parcel_id=parcel.id))