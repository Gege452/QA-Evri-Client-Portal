from datetime import datetime, timezone
from extensions import db

class Enquiry(db.Model):
    """
    Stores the main enquiry/ticket raised by a client.
    The original subject and message stay on this table.
    Follow-up discussion is stored in EnquiryComment.
    """

    id = db.Column(db.Integer, primary_key=True)
    created_by_user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)

    category = db.Column(db.String(80), nullable=False)
    tracking_number = db.Column(db.String(50), nullable=True)
    subject = db.Column(db.String(150), nullable=False)
    message = db.Column(db.Text, nullable=False)

    status = db.Column(db.String(30), nullable=False, default="New")

    created_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    closed_at = db.Column(db.DateTime, nullable=True)

    created_by = db.relationship("User", backref="enquiries")


class EnquiryComment(db.Model):
    """
    Stores follow-up comments added to an enquiry.
    User ID 1 is reserved for system-generated comments.
    """

    id = db.Column(db.Integer, primary_key=True)
    enquiry_id = db.Column(db.Integer, db.ForeignKey("enquiry.id"), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)

    comment = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))

    enquiry = db.relationship("Enquiry", backref="comments")
    user = db.relationship("User", backref="enquiry_comments")