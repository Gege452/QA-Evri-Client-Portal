from werkzeug.security import check_password_hash
from extensions import db

class User(db.Model):
    """
    Stores login accounts for both admin and client users.
    Passwords are stored as hashes, not plain text.
    """

    id = db.Column(db.Integer, primary_key=True)
    client_id = db.Column(db.Integer, db.ForeignKey("client.id"), nullable=True)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(20), nullable=False)  # admin or client
    display_name = db.Column(db.String(100), nullable=False)
    must_reset_password = db.Column(db.Boolean, default=False)
    is_active = db.Column(db.Boolean, default=True)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)