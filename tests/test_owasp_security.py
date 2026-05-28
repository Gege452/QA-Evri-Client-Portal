import pytest
from werkzeug.security import generate_password_hash, check_password_hash

from app import create_app
from extensions import db
from models import User, Client, Parcel, TrackEvent, Enquiry, EnquiryComment


@pytest.fixture()
# Create a test Flask application with an in-memory SQLite database and seeded test data
def app():
    test_app = create_app()
    test_app.config.update(
        TESTING=True,
        SQLALCHEMY_DATABASE_URI="sqlite:///:memory:",
        WTF_CSRF_ENABLED=False,
        SECRET_KEY="test-secret-key",
    )
    # Create the database and seed test data before yielding the app for testing
    with test_app.app_context():
        db.drop_all()
        db.create_all()
        seed_test_data()
        yield test_app
        db.session.remove()
        db.drop_all()


@pytest.fixture()
def client(app):
    # Create a test client for the Flask application
    return app.test_client()


def seed_test_data():
    # Create test users, clients, parcels, track events, enquiries, and comments for testing purposes
    system_user = User(
        id=1,
        email="system@evri.local",
        password_hash=generate_password_hash("SystemPassword123!"),
        role="system",
        display_name="System",
        must_reset_password=False,
        is_active=False,
    )

    admin_user = User(
        email="admin@evri.com",
        password_hash=generate_password_hash("AdminPassword123!"),
        role="admin",
        display_name="Admin User",
        must_reset_password=False,
        is_active=True,
    )

    client_one = Client(
        client_name="Client One",
        short_name="CLONE",
        status="Active",
        account_manager="Admin User",
        phone_number="07111111111",
        email="clientone@example.com",
        address_line_1="1 Test Street",
        postcode="TE1 1ST",
        country="United Kingdom",
        allow_stop_and_return=True,
    )

    client_two = Client(
        client_name="Client Two",
        short_name="CLTWO",
        status="Active",
        account_manager="Admin User",
        phone_number="07222222222",
        email="clienttwo@example.com",
        address_line_1="2 Test Street",
        postcode="TE2 2ST",
        country="United Kingdom",
        allow_stop_and_return=False,
    )

    db.session.add_all([system_user, admin_user, client_one, client_two])
    db.session.flush()

    client_one_user = User(
        email="clientone@example.com",
        password_hash=generate_password_hash("ClientPassword123!"),
        role="client",
        display_name="Client One",
        client_id=client_one.id,
        must_reset_password=False,
        is_active=True,
    )

    client_two_user = User(
        email="clienttwo@example.com",
        password_hash=generate_password_hash("ClientPassword123!"),
        role="client",
        display_name="Client Two",
        client_id=client_two.id,
        must_reset_password=False,
        is_active=True,
    )

    reset_required_user = User(
        email="resetclient@example.com",
        password_hash=generate_password_hash("TempPassword123!"),
        role="client",
        display_name="Reset Client",
        client_id=client_one.id,
        must_reset_password=True,
        is_active=True,
    )

    db.session.add_all([client_one_user, client_two_user, reset_required_user])
    db.session.flush()

    parcel_one = Parcel(
        tracking_number="H1111111111",
        client_id=client_one.id,
        created_by_user_id=client_one_user.id,
        parcel_size="Standard parcel",
        delivery_speed="Standard",
        parcel_contents="Books",
        parcel_value_gbp=20.00,
        recipient_first_name="John",
        recipient_last_name="Smith",
        recipient_address_line_1="10 Parcel Street",
        recipient_postcode="PA1 1AA",
        recipient_country="United Kingdom",
        status="In Transit",
    )

    parcel_two = Parcel(
        tracking_number="H2222222222",
        client_id=client_two.id,
        created_by_user_id=client_two_user.id,
        parcel_size="Standard parcel",
        delivery_speed="Standard",
        parcel_contents="Shoes",
        parcel_value_gbp=50.00,
        recipient_first_name="Jane",
        recipient_last_name="Jones",
        recipient_address_line_1="20 Parcel Street",
        recipient_postcode="PA2 2AA",
        recipient_country="United Kingdom",
        status="Delivered",
    )

    db.session.add_all([parcel_one, parcel_two])
    db.session.flush()

    track_event_one = TrackEvent(
        parcel_id=parcel_one.id,
        event_status="In Transit",
        event_location="National Hub",
        event_description="Parcel is moving through the network.",
        visible_to_client=True,
    )

    track_event_two = TrackEvent(
        parcel_id=parcel_two.id,
        event_status="Delivered",
        event_location="Delivery Unit",
        event_description="Parcel has been delivered.",
        visible_to_client=True,
    )

    enquiry = Enquiry(
        created_by_user_id=client_one_user.id,
        category="General enquiry",
        tracking_number=None,
        subject="Test enquiry",
        message="This is a test enquiry.",
        status="Work in Progress",
    )

    db.session.add_all([track_event_one, track_event_two, enquiry])
    db.session.flush()

    comment = EnquiryComment(
        enquiry_id=enquiry.id,
        user_id=client_one_user.id,
        comment="Client comment to be deleted by admin.",
    )

    db.session.add(comment)
    db.session.commit()

# Helper function to perform login in tests
def login(test_client, email, password):
    return test_client.post(
        "/login",
        data={
            "email": email,
            "password": password,
        },
        follow_redirects=True,
    )

def test_a01_client_cannot_access_admin_clients_page(client):
    # Log in as a client user
    login(client, "clientone@example.com", "ClientPassword123!")
    # Attempt to access the admin clients page
    response = client.get("/admin/clients", follow_redirects=True)
    # Verify that access is denied and the client is redirected to an appropriate page
    assert response.status_code == 200
    assert b"You do not have permission" in response.data or b"Client Portal" in response.data


def test_a01_client_cannot_view_another_clients_parcel(client):
    # Log in as client one and attempt to view a parcel that belongs to client two
    login(client, "clientone@example.com", "ClientPassword123!")
    # Parcel with tracking number H2222222222 belongs to client two, so client one should not be able to view it
    response = client.get("/client/parcel/2", follow_redirects=True)
    # Verify that access is denied and the client is redirected to an appropriate page
    assert response.status_code == 200
    assert b"You do not have permission" in response.data or b"Your parcels" in response.data


def test_a01_client_searching_other_clients_tracking_number_returns_no_results(client):
    # Log in as client one and attempt to search for a tracking number that belongs to client two
    login(client, "clientone@example.com", "ClientPassword123!")
    # Attempt to search for a tracking number that belongs to client two
    response = client.get(
        "/client/parcel?search_by=tracking_number&search_value=H2222222222",
        follow_redirects=True,
    )
    # Verify that no results are returned since the tracking number belongs to another client
    assert response.status_code == 200
    assert b"No parcels matched your search" in response.data


def test_a07_invalid_login_is_rejected(client):
    # Attempt to log in with valid email but incorrect password
    response = login(client, "admin@evri.com", "WrongPassword123!")
    # Verify that the login is rejected and an appropriate error message is displayed
    assert response.status_code == 200
    assert b"Invalid email address or password" in response.data


def test_a07_client_with_temporary_password_is_forced_to_reset(client):
    # Log in as the client user that has must_reset_password=True
    response = login(client, "resetclient@example.com", "TempPassword123!")
    # Verify that the client is redirected to the reset password page
    assert response.status_code == 200
    assert b"reset" in response.data.lower() or b"Reset password" in response.data


def test_a07_weak_reset_password_is_rejected(client):
    # Log in as the client user that has must_reset_password=True
    login(client, "resetclient@example.com", "TempPassword123!")
    # Attempt to reset the password to a weak password that does not meet the complexity requirements
    response = client.post(
        "/reset-password",
        data={
            "new_password": "password",
            "confirm_password": "password",
        },
        follow_redirects=True,
    )
    # Verify that the password reset is rejected and an appropriate error message is displayed
    assert response.status_code == 200
    assert b"Password must" in response.data


def test_a04_password_is_stored_as_hash(app):
    # Verify that the password for a user is stored as a hash and not in plaintext
    with app.app_context():
        # Retrieve the user from the database
        user = User.query.filter_by(email="clientone@example.com").first()
        # Verify that the user exists and that the password is stored as a hash
        assert user is not None
        assert user.password_hash != "ClientPassword123!"
        assert check_password_hash(user.password_hash, "ClientPassword123!")


def test_a05_sql_injection_style_login_does_not_bypass_authentication(client):
    # Attempt to log in using SQL injection style input that would bypass authentication if the input were not properly handled
    response = client.post(
        "/login",
        data={
            "email": "' OR '1'='1",
            "password": "' OR '1'='1",
        },
        follow_redirects=True,
    )
    # Verify that the login is rejected and an appropriate error message is displayed, indicating that authentication was not bypassed
    assert response.status_code == 200
    assert b"Invalid email address or password" in response.data


def test_a06_stop_and_return_allowed_when_parcel_in_transit_and_client_enabled(client, app):
    # Log in as client one, who has allow_stop_and_return=True, and attempt to stop and return a parcel that is currently in transit
    login(client, "clientone@example.com", "ClientPassword123!")
    # Parcel with tracking number H1111111111 belongs to client one and is currently in transit, so the stop and return request should be allowed
    response = client.post(
        "/parcel/1/stop-return",
        follow_redirects=True,
    )
    # Verify that the stop and return request is processed successfully and that the parcel status is updated accordingly
    assert response.status_code == 200
    # Verify that the parcel status is updated to "Stop and return" and that a corresponding track event is created
    with app.app_context():
        parcel = Parcel.query.filter_by(tracking_number="H1111111111").first()
        stop_return_event = TrackEvent.query.filter_by(
            parcel_id=parcel.id,
            event_status="Stop and return",
        ).first()
        # Verify that the parcel status is updated to "Stop and return" and that a corresponding track event is created
        assert parcel.status == "Stop and return"
        assert stop_return_event is not None


def test_a06_stop_and_return_rejected_when_parcel_already_delivered(client, app):
    # Log in as client two, who has allow_stop_and_return=False, and attempt to stop and return a parcel that is already delivered
    login(client, "clienttwo@example.com", "ClientPassword123!")
    # Parcel with tracking number H2222222222 belongs to client two and is already delivered, so the stop and return request should be rejected
    response = client.post(
        "/parcel/2/stop-return",
        follow_redirects=True,
    )
    # Verify that the stop and return request is rejected and that an appropriate error message is displayed, indicating that the parcel cannot be stopped and returned because it has already been delivered
    assert response.status_code == 200
    # Verify that the parcel status is not updated to "Stop and return" and that no corresponding track event is created
    with app.app_context():
        parcel = Parcel.query.filter_by(tracking_number="H2222222222").first()
        stop_return_event = TrackEvent.query.filter_by(
            parcel_id=parcel.id,
            event_status="Stop and return",
        ).first()

        assert parcel.status == "Delivered"
        assert stop_return_event is None


def test_a08_admin_track_event_updates_parcel_status(client, app):
    # Log in as admin user and update the track event for a parcel to a status that should update the parcel status accordingly
    login(client, "admin@evri.com", "AdminPassword123!")

    response = client.post(
        "/admin/parcel/1",
        data={
            "event_status": "Delayed",
            "event_location": "National Hub",
            "event_description": "Parcel is delayed.",
            "visible_to_client": "yes",
        },
        follow_redirects=True,
    )
    # Verify that the track event is updated successfully and that the parcel status is updated to "Delayed" as a result of the track event update
    assert response.status_code == 200

    with app.app_context():
        parcel = Parcel.query.filter_by(tracking_number="H1111111111").first()
        delayed_event = TrackEvent.query.filter_by(
            parcel_id=parcel.id,
            event_status="Delayed",
        ).first()

        assert parcel.status == "Delayed"
        assert delayed_event is not None


def test_a09_admin_deleting_enquiry_comment_creates_system_comment(client, app):
    # Log in as admin user and delete a comment on an enquiry that was made by a client user, then verify that the comment is deleted and that a new system comment is created indicating that the comment was deleted
    login(client, "admin@evri.com", "AdminPassword123!")
    # Retrieve an enquiry and a comment made by a client user to be deleted
    with app.app_context():
        enquiry = Enquiry.query.first()
        comment = EnquiryComment.query.filter(EnquiryComment.user_id != 1).first()
        enquiry_id = enquiry.id
        comment_id = comment.id
    # Delete the comment as the admin user
    response = client.post(
        f"/admin/enquiry/{enquiry_id}/comment/{comment_id}/delete",
        follow_redirects=True,
    )
    # Verify that the comment is deleted and that a new system comment is created indicating that the comment was deleted
    assert response.status_code == 200

    with app.app_context():
        deleted_comment = EnquiryComment.query.get(comment_id)
        system_comment = EnquiryComment.query.filter(
            EnquiryComment.enquiry_id == enquiry_id,
            EnquiryComment.user_id == 1,
            EnquiryComment.comment.ilike("%deleted a comment%"),
        ).first()

        assert deleted_comment is None
        assert system_comment is not None


def test_a10_missing_required_parcel_fields_show_validation_error(client):
    # Log in as client one and attempt to create a new parcel with missing required fields, then verify that the parcel creation is rejected and that appropriate validation error messages are displayed for the missing fields
    login(client, "clientone@example.com", "ClientPassword123!")

    response = client.post(
        "/client/parcel/create",
        data={
            "parcel_size": "",
            "delivery_speed": "",
            "parcel_contents": "",
            "parcel_value_gbp": "",
            "recipient_first_name": "",
            "recipient_last_name": "",
            "address_line_1": "",
            "postcode": "",
            "country": "",
        },
        follow_redirects=True,
    )
    # Verify that the parcel creation is rejected and that appropriate validation error messages are displayed for the missing fields
    assert response.status_code == 200
    assert b"required" in response.data.lower()