from werkzeug.security import generate_password_hash

from extensions import db
from models import Client, Enquiry, Parcel, TrackEvent, User


def login(client, email, password, follow_redirects=False):
    return client.post(
        "/login",
        data={"email": email, "password": password},
        follow_redirects=follow_redirects,
    )


def test_admin_login_redirects_to_admin_home(client, init_data):
    response = login(client, "admin@evri.com", "adminpass")

    assert response.status_code == 302
    assert "/admin/home" in response.headers["Location"]


def test_login_wrong_password_shows_error(client, init_data):
    response = login(client, "admin@evri.com", "wrongpass", follow_redirects=True)

    assert response.status_code == 200
    assert b"Invalid email address or password." in response.data
    assert b"LOG IN" in response.data


def test_client_cannot_access_admin_clients(client, init_data):
    response = login(client, "client@example.com", "clientpass")
    assert response.status_code == 302

    response = client.get("/admin/clients")
    assert response.status_code == 302
    assert "/client/home" in response.headers["Location"]


def test_client_cannot_view_other_client_parcel(client, app, init_data):
    with app.app_context():
        other_client = Client(
            client_name="Other Client Ltd",
            short_name="OTHR",
            status="Active",
            account_manager="Admin Tester",
            phone_number="01112223344",
            email="other@example.com",
            address_line_1="2 Other Street",
            postcode="OT5 7RS",
            country="United Kingdom",
            allow_stop_and_return=True,
        )
        db.session.add(other_client)
        db.session.flush()

        other_client_user = User(
            email="other_client@example.com",
            password_hash=generate_password_hash("otherpass"),
            role="client",
            display_name="Other Client",
            client_id=other_client.id,
            must_reset_password=False,
            is_active=True,
        )
        db.session.add(other_client_user)
        db.session.flush()

        parcel = Parcel(
            tracking_number="T01A000000000001",
            client_id=other_client.id,
            created_by_user_id=other_client_user.id,
            parcel_size="Standard parcel",
            delivery_speed="Standard",
            parcel_contents="Books",
            parcel_value_gbp=25.0,
            recipient_first_name="Sam",
            recipient_last_name="Other",
            recipient_address_line_1="10 Other Lane",
            recipient_postcode="OT10 9ZZ",
            recipient_country="United Kingdom",
        )
        db.session.add(parcel)
        db.session.commit()
        parcel_id = parcel.id

    response = login(client, "client@example.com", "clientpass")
    assert response.status_code == 302

    response = client.get(f"/client/parcel/{parcel_id}")
    assert response.status_code == 302
    assert "/client/parcel" in response.headers["Location"]


def test_create_parcel_required_fields_are_validated(client, init_data):
    login(client, "client@example.com", "clientpass")

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

    assert response.status_code == 200
    assert b"Please select a valid parcel size." in response.data
    assert b"Please select a valid delivery speed." in response.data
    assert b"Parcel contents" in response.data


def test_client_with_must_reset_password_is_forced_to_reset(client, app):
    with app.app_context():
        client_record = Client(
            client_name="Force Reset Ltd",
            short_name="FRC",
            status="Active",
            account_manager="Admin Tester",
            phone_number="01234000000",
            email="force@example.com",
            address_line_1="1 Reset Lane",
            postcode="RS5 7ER",
            country="United Kingdom",
            allow_stop_and_return=True,
        )
        db.session.add(client_record)
        db.session.flush()

        client_user = User(
            email="force@example.com",
            password_hash=generate_password_hash("Temp123!"),
            role="client",
            display_name="Reset Client",
            client_id=client_record.id,
            must_reset_password=True,
            is_active=True,
        )
        db.session.add(client_user)
        db.session.commit()

    response = login(client, "force@example.com", "Temp123!")
    assert response.status_code == 302
    assert "/reset-password" in response.headers["Location"]

    response = client.post(
        "/reset-password",
        data={"new_password": "Newpass1!", "confirm_password": "Newpass1!"},
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert b"Password reset successfully" in response.data

    with app.app_context():
        updated_user = User.query.filter_by(email="force@example.com").first()
        assert updated_user is not None
        assert updated_user.must_reset_password is False

    second_response = login(client, "force@example.com", "Temp123!", follow_redirects=True)
    assert b"Invalid email address or password." in second_response.data

    success_response = login(client, "force@example.com", "Newpass1!")
    assert success_response.status_code == 302
    assert "/client/home" in success_response.headers["Location"]


def test_client_can_create_enquiry_and_admin_can_view_it(client, app, init_data):
    login(client, "client@example.com", "clientpass")

    response = client.post(
        "/client/enquiry/new",
        data={
            "category": "General enquiry",
            "tracking_number": "",
            "subject": "Test enquiry subject",
            "message": "This is a test enquiry.",
        },
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert b"has been created successfully" in response.data

    with app.app_context():
        enquiry = Enquiry.query.filter_by(subject="Test enquiry subject").first()
        assert enquiry is not None
        assert enquiry.created_by_user_id == init_data["client_user_id"]

    client.get("/logout", follow_redirects=True)
    login(client, "admin@evri.com", "adminpass")

    response = client.get("/admin/enquiries")
    assert response.status_code == 200
    assert b"Test enquiry subject" in response.data


def test_creating_parcel_creates_first_track_event(client, app, init_data):
    login(client, "client@example.com", "clientpass")

    response = client.post(
        "/client/parcel/create",
        data={
            "parcel_size": "Standard parcel",
            "delivery_speed": "Standard",
            "parcel_contents": "Test box",
            "parcel_value_gbp": "40.00",
            "recipient_first_name": "Rich",
            "recipient_last_name": "Client",
            "address_line_1": "10 Parcel Road",
            "address_line_2": "",
            "address_line_3": "",
            "address_line_4": "",
            "postcode": "PA1 7ST",
            "country": "United Kingdom",
        },
        follow_redirects=True,
    )

    assert response.status_code == 200

    with app.app_context():
        parcel = Parcel.query.filter_by(created_by_user_id=init_data["client_user_id"]).first()
        assert parcel is not None

        track_events = TrackEvent.query.filter_by(parcel_id=parcel.id).all()
        assert len(track_events) == 1
        assert track_events[0].event_status == "Label Generated"


def test_stop_and_return_only_allowed_when_conditions_are_met(client, app, init_data):
    with app.app_context():
        parcel = Parcel(
            tracking_number="T02A000000000002",
            client_id=init_data["client_record_id"],
            created_by_user_id=init_data["client_user_id"],
            parcel_size="Standard parcel",
            delivery_speed="Standard",
            parcel_contents="Gadgets",
            parcel_value_gbp=75.0,
            recipient_first_name="Olly",
            recipient_last_name="Client",
            recipient_address_line_1="3 Client Curve",
            recipient_postcode="CL1 7NT",
            recipient_country="United Kingdom",
        )
        db.session.add(parcel)
        db.session.flush()

        event = TrackEvent(
            parcel_id=parcel.id,
            event_status="In Transit",
            event_location="Client Portal",
            event_description="Parcel is in transit.",
            visible_to_client=True,
        )
        db.session.add(event)
        db.session.commit()
        parcel_id = parcel.id

    login(client, "client@example.com", "clientpass")
    response = client.post(f"/parcel/{parcel_id}/stop-return", follow_redirects=False)

    assert response.status_code == 302
    assert f"/client/parcel/{parcel.id}" in response.headers["Location"]

    with app.app_context():
        updated_parcel = Parcel.query.get(parcel_id)
        assert updated_parcel.status == "Stop and return"


def test_stop_and_return_blocked_when_status_is_delivered(client, app, init_data):
    with app.app_context():
        parcel = Parcel(
            tracking_number="T03A000000000003",
            client_id=init_data["client_record_id"],
            created_by_user_id=init_data["client_user_id"],
            parcel_size="Standard parcel",
            delivery_speed="Standard",
            parcel_contents="Gadgets",
            parcel_value_gbp=75.0,
            recipient_first_name="Olly",
            recipient_last_name="Client",
            recipient_address_line_1="3 Client Curve",
            recipient_postcode="CL1 7NT",
            recipient_country="United Kingdom",
        )
        db.session.add(parcel)
        db.session.flush()

        event = TrackEvent(
            parcel_id=parcel.id,
            event_status="Delivered",
            event_location="Client Portal",
            event_description="Parcel has been delivered.",
            visible_to_client=True,
        )
        db.session.add(event)
        db.session.commit()
        parcel_id = parcel.id

    login(client, "client@example.com", "clientpass")
    response = client.post(f"/parcel/{parcel_id}/stop-return", follow_redirects=True)

    assert response.status_code == 200
    assert b"Stop and Return is only available" in response.data
