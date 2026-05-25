from datetime import datetime, timezone
from extensions import db

class Client(db.Model):
    """
    Stores client/company records managed by admin users.
    """

    id = db.Column(db.Integer, primary_key=True)
    #ID is the primary key for the client record.

    client_name = db.Column(db.String(120), nullable=False)
    # Client name is the full name of the client/company, for example 'Acme Corporation'.

    short_name = db.Column(db.String(4), nullable=False)
    # Short name is used in the tracking reference for easier identification of the client.

    status = db.Column(db.String(8), nullable=False, default="Pending")
    # Status can be Pending, Active or Inactive.

    account_manager = db.Column(db.String(100), nullable=False)
    # Account manager is the name of the Evri employee responsible for managing the client relationship.

    phone_number = db.Column(db.String(31), nullable=False)
    email = db.Column(db.String(120), nullable=False)

    address_line_1 = db.Column(db.String(120), nullable=False)
    address_line_2 = db.Column(db.String(120), nullable=True)
    address_line_3 = db.Column(db.String(120), nullable=True)
    address_line_4 = db.Column(db.String(120), nullable=True)
    postcode = db.Column(db.String(20), nullable=False)
    country = db.Column(db.String(80), nullable=False)

    allow_stop_and_return = db.Column(db.Boolean, nullable=False, default=False)
    # Allow stop and return is a flag indicating whether the client is allowed to stop and return shipments.

    created_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))