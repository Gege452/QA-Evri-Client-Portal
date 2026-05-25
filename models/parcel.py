from datetime import datetime, timezone
from extensions import db

class Parcel(db.Model):
    """
    Stores parcel records created by client users.
    The current parcel status is stored here, while status history is stored in TrackEvent.
    """

    id = db.Column(db.Integer, primary_key=True)

    tracking_number = db.Column(db.String(16), unique=True, nullable=False)
    client_id = db.Column(db.Integer, db.ForeignKey("client.id"), nullable=False)
    created_by_user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)

    parcel_size = db.Column(db.String(31), nullable=False)
    delivery_speed = db.Column(db.String(8), nullable=False)

    parcel_contents = db.Column(db.String(32), nullable=False)
    parcel_value_gbp = db.Column(db.Float, nullable=False)

    recipient_first_name = db.Column(db.String(50), nullable=False)
    recipient_last_name = db.Column(db.String(50), nullable=False)

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