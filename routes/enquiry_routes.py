from flask import Blueprint, render_template, request, redirect, url_for, session, flash, current_app
from datetime import datetime, timezone

from auth_utils import role_required
from extensions import db, limiter
from models import Enquiry, EnquiryComment, Client, User
from config import ENQUIRY_CATEGORIES
from helpers import add_system_comment, create_enquiry_comment_object, create_enquiry_object, enquiry_requires_attention, format_enquiry_number, update_enquiry, build_enquiry_change_comment
from validators import validate

enquiry_bp = Blueprint("enquiry", __name__)

@enquiry_bp.route("/client/enquiries")
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

    enquiry_notifications = {
        enquiry.id: enquiry_requires_attention(enquiry, "client")
        for enquiry in enquiries
    }

    return render_template(
        "enquiries.html",
        enquiries=enquiries,
        enquiry_notifications=enquiry_notifications,
        role="client",
        portal_title="Client Portal",
        page_title="Enquiries",
        active_page="enquiries",
        email=session.get("email"),
        search_by=search_by,
        search_value=search_value,
    )

@enquiry_bp.route("/admin/enquiries")
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
        
        elif search_by == "client_name":
            query = (
                query
                .join(Enquiry.created_by)
                .join(Client, User.client_id == Client.id)
                .filter(Client.client_name.ilike(f"%{search_value}%"))
            )

        elif search_by == "subject":
            query = query.filter(Enquiry.subject.ilike(f"%{search_value}%"))

        elif search_by == "status":
            query = query.filter(Enquiry.status.ilike(f"%{search_value}%"))

    enquiries = query.order_by(Enquiry.created_at.desc()).all()

    enquiry_notifications = {
        enquiry.id: enquiry_requires_attention(enquiry, "admin")
        for enquiry in enquiries
    }

    return render_template(
        "enquiries.html",
        enquiries=enquiries,
        enquiry_notifications=enquiry_notifications,
        role="admin",
        portal_title="Admin Portal",
        page_title="Enquiries",
        active_page="enquiries",
        email=session.get("email"),
        search_by=search_by,
        search_value=search_value,
    )

@enquiry_bp.route("/client/enquiry/new", methods=["GET", "POST"])
@limiter.limit("10 per minute", methods=["POST"])
@role_required("client")
def new_client_enquiry():
    if request.method == "POST":
        category = request.form.get("category", "").strip()
        tracking_number = request.form.get("tracking_number", "").strip()
        subject = request.form.get("subject", "").strip()
        message = request.form.get("message", "").strip()

        errors = []

        errors.extend(validate(category, "Category", ["required", "enquiry_category"]))
        errors.extend(validate(tracking_number, "Tracking number", ["required_if_parcel", "match_length:16"], context={"category": category}))
        errors.extend(validate(subject, "Subject", ["required"]))
        errors.extend(validate(message, "Message", ["required"]))

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

        enquiry = create_enquiry_object(session["user_id"], category, subject, message, tracking_number=(tracking_number if tracking_number else None))

        db.session.add(enquiry)
        db.session.commit()

        system_comment = create_enquiry_comment_object(enquiry.id, 1, f"Enquiry ENQ{enquiry.id:06d} was created.")

        db.session.add(system_comment)
        db.session.commit()

        current_app.logger.info(
            "Client User (ID: %s) created enquiry (ID: %s).",
            session["user_id"],
            enquiry.id
        )

        flash(f"Enquiry ENQ{enquiry.id:06d} has been created successfully.", "success")
        return redirect(url_for("client.client_home"))

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


@enquiry_bp.route("/client/enquiry/<int:enquiry_id>", methods=["GET", "POST"])
@limiter.limit("10 per minute", methods=["POST"])
@role_required("client")
def client_view_enquiry(enquiry_id):
    enquiry = Enquiry.query.get_or_404(enquiry_id)

    # Client can only view their own enquiries.
    if enquiry.created_by_user_id != session["user_id"]:
        flash("You do not have permission to view that enquiry.", "error")
        return redirect(url_for("enquiry.client_enquiries"))

    if request.method == "POST":
        action = request.form.get("action")
        comment_text = request.form.get("comment", "").strip()

        if action == "add_comment":
            if enquiry.status == "Closed":
                flash("This enquiry is closed and cannot be updated.", "error")
                return redirect(url_for("enquiry.client_view_enquiry", enquiry_id=enquiry.id))

            if not comment_text:
                flash("Comment cannot be empty.", "error")
                return redirect(url_for("enquiry.client_view_enquiry", enquiry_id=enquiry.id))

            comment = create_enquiry_comment_object(enquiry.id, session["user_id"], comment_text)

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

            current_app.logger.info(
                "Client User (ID: %s) added a comment to enquiry (ID: %s).",
                session["user_id"],
                enquiry.id
            )

            flash("Comment added successfully.", "success")
            return redirect(url_for("enquiry.client_view_enquiry", enquiry_id=enquiry.id))

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

            current_app.logger.info(
                "Client User (ID: %s) closed enquiry (ID: %s).",
                session["user_id"],
                enquiry.id
            )

            flash("Enquiry closed successfully.", "success")
            return redirect(url_for("enquiry.client_view_enquiry", enquiry_id=enquiry.id))

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
    

@enquiry_bp.route("/admin/enquiry/<int:enquiry_id>", methods=["GET", "POST"])
@limiter.limit("10 per minute", methods=["POST"])
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

            errors = []

            errors.extend(validate(category, "Category", ["required", "enquiry_category"]))
            errors.extend(validate(tracking_number, "Tracking number", ["required_if_parcel", "match_length:16"], context={"category": category}))
            errors.extend(validate(subject, "Subject", ["required"]))
            errors.extend(validate(message, "Message", ["required"]))
            errors.extend(validate(status, "Status", ["required", "enquiry_status"]))

            if errors:
                for error in errors:
                    flash(error, "error")
                return redirect(url_for("enquiry.admin_view_enquiry", enquiry_id=enquiry.id))

            # Capture old values before updating so we can produce a detailed change summary
            old_values = {
                "category": enquiry.category,
                "tracking_number": enquiry.tracking_number,
                "subject": enquiry.subject,
                "message": enquiry.message,
                "status": enquiry.status,
            }
            
            update_enquiry(enquiry, category=category, tracking_number=(tracking_number if tracking_number else None), subject=subject, message=message, status=status, closed_at=(now if status == "Closed" else None))
            
            new_values = {
                "category": category,
                "tracking_number": tracking_number if tracking_number else None,
                "subject": subject,
                "message": message,
                "status": status,
            }

            change_comment = build_enquiry_change_comment(old_values, new_values, session.get("display_name"))
            if change_comment:
                add_system_comment(enquiry.id, change_comment)

            db.session.commit()

            current_app.logger.info(
                "Admin User (ID: %s) updated enquiry (ID: %s).",
                session["user_id"],
                enquiry.id,
            )

            flash("Enquiry updated successfully.", "success")
            return redirect(url_for("enquiry.admin_view_enquiry", enquiry_id=enquiry.id))

        if action == "add_comment":
            comment_text = request.form.get("comment", "").strip()

            if enquiry.status == "Closed":
                flash("This enquiry is closed and cannot be updated.", "error")
                return redirect(url_for("enquiry.admin_view_enquiry", enquiry_id=enquiry.id))

            if not comment_text:
                flash("Comment cannot be empty.", "error")
                return redirect(url_for("enquiry.admin_view_enquiry", enquiry_id=enquiry.id))

            comment = create_enquiry_comment_object(enquiry.id, session["user_id"], comment_text)

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
            return redirect(url_for("enquiry.admin_view_enquiry", enquiry_id=enquiry.id))

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

@enquiry_bp.route("/admin/enquiry/<int:enquiry_id>/comment/<int:comment_id>/delete", methods=["POST"])
@limiter.limit("10 per minute", methods=["POST"])
@role_required("admin")
def admin_delete_enquiry_comment(enquiry_id, comment_id):
    enquiry = Enquiry.query.get_or_404(enquiry_id)
    comment = EnquiryComment.query.get_or_404(comment_id)

    if comment.enquiry_id != enquiry.id:
        flash("Comment does not belong to this enquiry.", "error")
        return redirect(url_for("enquiry.admin_view_enquiry", enquiry_id=enquiry.id))

    # Do not allow deletion of system-generated comments.
    if comment.user_id == 1:
        flash("System comments cannot be deleted.", "error")
        return redirect(url_for("enquiry.admin_view_enquiry", enquiry_id=enquiry.id))

    current_app.logger.info(
        "Admin User (ID: %s) deleted a comment (ID: %s) from enquiry (ID: %s).",
        session["user_id"],
        comment.id,
        enquiry.id,
    )
    
    db.session.delete(comment)

    enquiry.updated_at = datetime.now(timezone.utc)

    add_system_comment(
        enquiry.id,
        f"{session['display_name']} deleted a comment from this enquiry."
    )

    db.session.commit()

    flash("Comment deleted successfully.", "success")
    return redirect(url_for("enquiry.admin_view_enquiry", enquiry_id=enquiry.id))
