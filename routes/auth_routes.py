from flask import Blueprint, render_template, request, redirect, url_for, session, flash
from werkzeug.security import generate_password_hash
from datetime import datetime, timezone

from auth_utils import login_required
from extensions import db
from models import User
from validators import validate_password_strength


auth_bp = Blueprint("auth", __name__)

@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")

        user = User.query.filter_by(email=email).first()

        if not user or not user.check_password(password):
            flash("Invalid email address or password.", "error")
            return redirect(url_for("auth.login"))

        if not user.is_active:
            flash("This account is inactive. Please contact an administrator.", "error")
            return redirect(url_for("auth.login"))

        session["user_id"] = user.id
        session["email"] = user.email
        session["role"] = user.role
        session["display_name"] = user.display_name

        if user.must_reset_password:
            flash("You must reset your password before accessing the portal.", "error")
            return redirect(url_for("auth.reset_password"))

        flash("Successfully logged in.", "success")

        if user.role == "admin":
            return redirect(url_for("admin.admin_home"))

        return redirect(url_for("client.client_home"))

    return render_template("login.html")

@auth_bp.route("/logout")
@login_required
def logout():
    session.clear()
    flash("Successfully logged out.", "success")
    return render_template("logout.html")

@auth_bp.route("/reset-password", methods=["GET", "POST"])
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

            return redirect(url_for("auth.reset_password"))

        user.password_hash = generate_password_hash(new_password)
        user.must_reset_password = False

        if hasattr(user, "updated_at"):
            user.updated_at = datetime.now(timezone.utc)

        db.session.commit()

        session.clear()

        flash("Password reset successfully. Please log in with your new password.", "success")
        return redirect(url_for("auth.login"))

    return render_template(
        "reset_password.html",
        page_title="Reset Password",
        email=session.get("email"),
    )