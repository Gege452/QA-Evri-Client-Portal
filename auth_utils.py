from functools import wraps
from flask import session, flash, redirect, url_for


def login_required(view_function):
    @wraps(view_function)
    def wrapper(*args, **kwargs):
        if "user_id" not in session:
            flash("Please log in to access the portal.", "error")
            return redirect(url_for("auth.login"))

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
                return redirect(url_for("auth.login"))

            if session.get("role") != required_role:
                flash("You do not have permission to access that page.", "error")

                if session.get("role") == "admin":
                    return redirect(url_for("admin.admin_home"))

                return redirect(url_for("client.client_home"))

            return view_function(*args, **kwargs)

        return wrapper

    return decorator