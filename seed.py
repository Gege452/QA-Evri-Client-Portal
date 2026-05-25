from datetime import datetime, timezone, timedelta
import random
import string
from werkzeug.security import generate_password_hash

from extensions import db
from models import User, Client, Enquiry, EnquiryComment, Parcel, TrackEvent


def _rand_name(prefix, i):
    return f"{prefix} {i:02d}"


def _rand_short_name(i):
    # produce a 3-4 letter uppercase short name
    letters = string.ascii_uppercase
    return (letters[i % 26] + letters[(i+1) % 26] + letters[(i+2) % 26])[:4]


def _rand_tracking_number(i):
    # 12-16 char alphanumeric
    rand = ''.join(random.choices(string.ascii_uppercase + string.digits, k=12))
    return f"T{i:04d}{rand}"


def _rand_postcode(i):
    return f"PC{i:03d} {i%10}AB"


def create_database_and_seed_users():
    db.create_all()

    # If we already have users, assume the DB is seeded.
    if User.query.first():
        print("Database already seeded")
        return

    now = datetime.now(timezone.utc)

    # Create system user (user_id==1)
    system_user = User(
        email="system@evri.com",
        password_hash=generate_password_hash("system"),
        role="admin",
        display_name="System",
        must_reset_password=False,
        is_active=False,
    )
    db.session.add(system_user)
    db.session.flush()

    # Create 5 admin users with @evri.com
    admin_users = []
    for i in range(1, 6):
        email = f"admin{i}@evri.com"
        admin = User(
            email=email,
            password_hash=generate_password_hash("adminpass"),
            role="admin",
            display_name=_rand_name("Admin", i),
            must_reset_password=False,
            is_active=True,
        )
        db.session.add(admin)
        admin_users.append(admin)

    db.session.flush()

    # Create 10 clients each with a primary client user
    clients = []
    client_users = []
    for i in range(1, 11):
        client = Client(
            client_name=_rand_name("Client", i),
            short_name=_rand_short_name(i),
            status="Active",
            account_manager=admin_users[i % len(admin_users)].display_name,
            phone_number=f"07{random.randint(100000000,999999999)}",
            email=f"client{i}@example.com",
            address_line_1=f"{i} Example Street",
            address_line_2=None,
            address_line_3=None,
            address_line_4=None,
            postcode=_rand_postcode(i),
            country="United Kingdom",
            allow_stop_and_return=bool(i % 2),
            created_at=now - timedelta(days=30-i),
            updated_at=now - timedelta(days=30-i),
        )
        db.session.add(client)
        db.session.flush()

        user = User(
            email=f"user{i}@{client.short_name.lower()}.local",
            password_hash=generate_password_hash("clientpass"),
            role="client",
            display_name=client.client_name,
            client_id=client.id,
            must_reset_password=True,
            is_active=True,
        )
        db.session.add(user)

        clients.append(client)
        client_users.append(user)

    db.session.flush()

    # For each client create 10 parcels, each with 5 track events
    parcel_statuses = [
        "Label Generated",
        "In Transit",
        "Out for Delivery",
        "Delivered",
        "Exception",
    ]

    created_parcels = []
    for ci, client in enumerate(clients, start=1):
        creator = client_users[ci-1]
        for p in range(1, 11):
            tracking_number = _rand_tracking_number(ci*100 + p)
            parcel = Parcel(
                tracking_number=tracking_number,
                client_id=client.id,
                created_by_user_id=creator.id,
                parcel_size=random.choice(["Standard parcel", "Postable parcel or large letter"]),
                delivery_speed=random.choice(["Standard", "Next Day"]),
                parcel_contents="Books",
                parcel_value_gbp=round(random.uniform(1.0, 500.0), 2),
                recipient_first_name="Recipient",
                recipient_last_name=f"{p}",
                recipient_address_line_1=f"{p} Recipient Road",
                recipient_address_line_2=None,
                recipient_address_line_3=None,
                recipient_address_line_4=None,
                recipient_postcode=_rand_postcode(p),
                recipient_country="United Kingdom",
                status=random.choice(parcel_statuses),
                created_at=now - timedelta(days=random.randint(1, 20)),
                updated_at=now,
            )
            db.session.add(parcel)
            db.session.flush()

            # Add 5 track events per parcel
            for te in range(5):
                event = TrackEvent(
                    parcel_id=parcel.id,
                    event_status=random.choice(parcel_statuses),
                    event_location=f"Hub {random.randint(1,10)}",
                    event_description="Automated seed event",
                    visible_to_client=True,
                    created_at=now - timedelta(days=random.randint(0, 10), hours=random.randint(0,23)),
                )
                db.session.add(event)

            created_parcels.append(parcel)

    db.session.flush()

    # For each client create 5 enquiries, each with 5 comments (system, admin, client, admin, client)
    for ci, client in enumerate(clients, start=1):
        client_user = client_users[ci-1]
        for e in range(1, 6):
            enquiry = Enquiry(
                created_by_user_id=client_user.id,
                category=random.choice(["General enquiry", "Account issue", "Billing issue"]),
                tracking_number=None,
                subject=f"Enquiry {ci}-{e}",
                message="This is a seeded enquiry message.",
                status="New",
                created_at=now - timedelta(days=random.randint(0, 30)),
                updated_at=now,
            )
            db.session.add(enquiry)
            db.session.flush()

            # Add 5 comments: system, admin, client, admin, client
            comments = []
            comments.append(EnquiryComment(enquiry_id=enquiry.id, user_id=system_user.id, comment=f"Enquiry {enquiry.id} created by system.", created_at=now))
            admin_for_comment = random.choice(admin_users)
            comments.append(EnquiryComment(enquiry_id=enquiry.id, user_id=admin_for_comment.id, comment="Admin note: reviewed.", created_at=now))
            comments.append(EnquiryComment(enquiry_id=enquiry.id, user_id=client_user.id, comment="Client reply: please advise.", created_at=now))
            comments.append(EnquiryComment(enquiry_id=enquiry.id, user_id=admin_for_comment.id, comment="Admin update: actioned.", created_at=now))
            comments.append(EnquiryComment(enquiry_id=enquiry.id, user_id=client_user.id, comment="Client confirmation: thanks.", created_at=now))

            for c in comments:
                db.session.add(c)

    db.session.commit()

    print("Database seeded: admins, clients, parcels, track events, enquiries, and comments created.")

