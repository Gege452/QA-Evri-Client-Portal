import re

from models import User, Client
from extensions import db
from config import ENQUIRY_CATEGORIES, ENQUIRY_STATUS_OPTIONS, PARCEL_RELATED_CATEGORIES, CLIENT_STATUS_OPTIONS

def validate(value, field_name, rules, context=None):
    """
    Validates a single field value against a list of rules.
    
    Args:
        value: The value to validate
        field_name: Display name of the field
        rules: List of rules to apply
        context: Optional dictionary with additional context for conditional validation
    
    Example:
        validate(tracking_number, "Tracking Number", ["required_if_parcel"], 
                 context={"category": category})
        This would validate that the tracking number is provided if the category is one of the parcel-related categories.

        validate_form(address_line_1, "Address line 1", ["required", "max_length:120"])
            This would validate that the address line 1 is provided and does not exceed 120 characters.
    """

    if context is None:
        context = {}

    errors = []

    if isinstance(value, str):
        value = value.strip()

    for rule in rules:
        if rule == "required":
            if value is None or value == "":
                errors.append(f"The {field_name} field is required.")

        elif rule.startswith("max_length:"):
            max_length = int(rule.split(":")[1])

            if value and len(value) > max_length:
                errors.append(f"The {field_name} field must be {max_length} characters or fewer.")

        elif rule.startswith("min_length:"):
            min_length = int(rule.split(":")[1])

            if value and len(value) < min_length:
                errors.append(f"The {field_name} field must be at least {min_length} characters.")

        elif rule == "email":
            if value and not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", value):
                errors.append(f"The {field_name} field must be a valid email address.")

        elif rule == "client_status":
            if value not in CLIENT_STATUS_OPTIONS:
                errors.append(f"The {field_name} field must be one of: {', '.join(CLIENT_STATUS_OPTIONS)}.")

        elif rule == "enquiry_category":
            if value not in ENQUIRY_CATEGORIES:
                errors.append(f"The {field_name} field must be a valid enquiry category.")

        elif rule == "enquiry_status":
            if value not in ENQUIRY_STATUS_OPTIONS:
                errors.append(f"The {field_name} field must be one of: {', '.join(ENQUIRY_STATUS_OPTIONS)}.")

        elif rule == "required_if_parcel":
            category = context.get("category")
            if category in PARCEL_RELATED_CATEGORIES and not value:
                errors.append("Tracking number is required for parcel-related enquiries.")

        elif rule == "gbp":
            if value and not re.match(r"^\d+\.\d{2}$", value):
                errors.append(f"The {field_name} field must be a valid GBP amount (e.g., 10.99).")

        elif rule.startswith("max_value:"):
            max_value = float(rule.split(":")[1])
            if value:
                try:
                    num_value = float(value)
                    if num_value > max_value:
                        errors.append(f"The {field_name} field must be {max_value} or less.")
                except ValueError:
                    errors.append(f"The {field_name} field must be a valid number.")

        elif rule.startswith("min_value:"):
            min_value = float(rule.split(":")[1])
            if value:
                try:
                    num_value = float(value)
                    if num_value < min_value:
                        errors.append(f"The {field_name} field must be {min_value} or greater.")
                except ValueError:
                    errors.append(f"The {field_name} field must be a valid number.")
        # elif rule == "positive_number":
        #     try:
        #         number_value = float(value)

        #         if number_value < 0:
        #             errors.append(f"The {field_name} field cannot be negative.")
        #     except ValueError:
        #         errors.append(f"The {field_name} field must be a valid number.")

    return errors


def validate_password_strength(password):
    """
    Validates that a password meets certain strength criteria:
    - At least 8 characters long
    - Contains at least one uppercase letter
    - Contains at least one lowercase letter
    - Contains at least one number
    - Contains at least one special character
    
    Returns a list of error messages if the password does not meet the criteria.
    If the list is empty, the password is considered strong.
    """
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
        errors.append(
            "Password must contain at least one special character: ! @ # $ % & *"
        )

    return errors

def is_email_taken(email):
    """
    Checks if an email address is already taken by another user.
    """
    errors = []

    existing_user = User.query.filter(User.email == email).first()

    if existing_user:
        errors.append("This email address is already used by another account.")

    return errors

def is_client_name_taken(client_name, client_id=None):
    """
    Checks if a client name is already taken by another client.
    """
    errors = []

    existing_client = Client.query.filter(
        db.func.lower(Client.client_name) == client_name.lower(), Client.id != client_id
    ).first()

    if existing_client:
        errors.append("A client already exists with this client name.")

    return errors

def is_client_short_name_taken(short_name, client_id=None):
    """
    Checks if a client short name is already taken by another client.
    """
    errors = []

    existing_short_name = Client.query.filter(
        db.func.lower(Client.short_name) == short_name.lower(), Client.id != client_id
    ).first()

    if existing_short_name:
        errors.append("A client already exists with this short name.")

    return errors

def validate_new_email(new_email, confirm_email, user):
    """
    Validates new email address and confirmation email for account updates.
    Email update is optional, but if one field is filled, both must match.
    Returns a list of error messages if the validation fails.
    """

    errors = []

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

    return errors

def validate_new_phone_number(new_phone_number, confirm_phone_number):
    """
    Validates new phone number and confirmation phone number for account updates.
    Phone update is optional, but if one field is filled, both must match.
    Returns a list of error messages if the validation fails.
    """

    errors = []

    if new_phone_number or confirm_phone_number:
        if not new_phone_number:
            errors.append("New phone number is required.")
        if not confirm_phone_number:
            errors.append("Please confirm the new phone number.")
        if new_phone_number and confirm_phone_number and new_phone_number != confirm_phone_number:
            errors.append("New phone number and confirmation phone number do not match.")

    return errors