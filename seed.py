from datetime import datetime, timezone, timedelta
import random
import string
from werkzeug.security import generate_password_hash

from extensions import db
from models import User, Client, Enquiry, EnquiryComment, Parcel, TrackEvent
from helpers import create_enquiry_object, update_enquiry, create_enquiry_comment_object, build_enquiry_change_comment, generate_tracking_number


def _rand_name(prefix, i):
    return f"{prefix} {i:02d}"


def _rand_short_name(i):
    # produce a 3-4 letter uppercase short name
    letters = string.ascii_uppercase
    return (letters[i % 26] + letters[(i+1) % 26] + letters[(i+2) % 26])[:4]


def _rand_tracking_number(i):
    # Use canonical generator from helpers to ensure format consistency (16 chars)
    return generate_tracking_number()


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
            password_hash=generate_password_hash("AdminPass123!"),
            role="admin",
            display_name=_rand_name("Admin", i),
            must_reset_password=False,
            is_active=True,
        )
        db.session.add(admin)
        admin_users.append(admin)

    db.session.flush()

    # Small name and city pools used for client realism
    recipient_first_names = [
        "Alex", "Jamie", "Sam", "Taylor", "Jordan", "Casey", "Morgan", "Riley", "Charlie", "Avery",
    ]

    recipient_last_names = [
        "Smith", "Brown", "Johnson", "Taylor", "Davies", "Wilson", "Evans", "Thomas", "Robinson", "Wright",
    ]

    cities = [
        "Leeds", "Rugby", "Warrington", "Morley", "Manchester", "Birmingham", "London", "Leicester", "Hull", "Liverpool",
    ]

    # Create 10 clients each with a primary client user. Vary completeness: some only required fields, some full profiles.
    clients = []
    client_users = []
    for i in range(1, 11):
        client_name = _rand_name("Client", i)
        short = _rand_short_name(i)

        # Decide how much data this client will have
        completeness = random.choices(["required", "partial", "full"], weights=[2, 3, 5])[0]

        # Make an account manager name from the name pools
        account_manager = f"{random.choice(recipient_first_names)} {random.choice(recipient_last_names)}"

        # Business-looking email derived from short name
        domain = f"{short.lower()}.co.uk"
        email = f"contact@{domain}"

        city = random.choice(cities)

        # Required address line
        address_line_1 = f"{i} {random.choice(['High Street','Station Road','Business Park','Industrial Estate'])}, {city}"

        # Optional address lines
        if completeness == "full":
            address_line_2 = f"Suite {random.randint(1, 50)}"
            address_line_3 = f"{random.choice(['Building A','Block B','Unit C']) }"
            address_line_4 = f"{random.choice(['North','South','East','West']) }"
        elif completeness == "partial":
            address_line_2 = f"{random.choice(['Floor 1','Floor 2','Unit 4']) }"
            address_line_3 = None
            address_line_4 = None
        else:
            address_line_2 = None
            address_line_3 = None
            address_line_4 = None

        # Random phone and stop-and-return permission
        phone_number = f"07{random.randint(100000000,999999999)}"
        allow_stop = random.choice([True, False])

        # Created some clients recently and some older
        created_delta_days = random.randint(0, 365 * 3)
        created_at = now - timedelta(days=created_delta_days)
        updated_at = created_at + timedelta(days=random.randint(0, max(0, 90 - (created_delta_days % 90))))

        status = random.choice(["Active", "Pending", "Inactive"])

        client = Client(
            client_name=client_name,
            short_name=short,
            status=status,
            account_manager=account_manager,
            phone_number=phone_number,
            email=email,
            address_line_1=address_line_1,
            address_line_2=address_line_2,
            address_line_3=address_line_3,
            address_line_4=address_line_4,
            postcode=_rand_postcode(i),
            country="United Kingdom",
            allow_stop_and_return=allow_stop,
            created_at=created_at,
            updated_at=updated_at
        )
        db.session.add(client)
        db.session.flush()

        user = User(
            email=f"user{i}@{short.lower()}.local",
            password_hash=generate_password_hash("ClientPass123!"),
            role="client",
            display_name=client.client_name,
            client_id=client.id,
            must_reset_password=True,
            is_active=(True if status == "Active" else False)
        )
        db.session.add(user)

        clients.append(client)
        client_users.append(user)

    db.session.flush()

    # Create varied parcels and realistic TrackEvent timelines per client
    parcel_contents_options = [
        "Books",
        "Clothing",
        "Electronics",
        "Household goods",
        "Shoes",
        "Toys",
        "Documents",
        "Fragile items",
        "Cosmetics",
        "Sports equipment",
    ]

    recipient_first_names = ["Alex", "Jamie", "Sam", "Taylor", "Jordan", "Casey", "Morgan", "Riley", "Charlie", "Avery"]
    recipient_last_names = ["Smith", "Brown", "Johnson", "Taylor", "Davies", "Wilson", "Evans", "Thomas", "Robinson", "Wright"]

    cities = ["Leeds", "Rugby", "Warrington", "Morley", "Manchester", "Birmingham", "London", "Leicester", "Hull", "Liverpool"]

    # Scenarios to rotate across parcels: label only, in-transit (visible), in-transit (hidden extra), hub->depot->DU chain, out-for-delivery, delivered, delayed (visible + hidden), stop-and-return, returned-then-delivered, cancelled
    scenario_names = [
        "label_only",
        "in_transit_visible",
        "in_transit_hidden",
        "hub_depot_du",
        "out_for_delivery",
        "delivered",
        "delayed_with_hidden_reason",
        "stop_and_return",
        "returned_then_delivered",
        "cancelled_after_in_transit",
    ]

    for ci, client in enumerate(clients, start=1):
        creator = client_users[ci-1]
        # choose a base city for this client to use as initial location
        base_city = random.choice(cities)

        for p in range(1, 11):
            scenario = scenario_names[(p - 1) % len(scenario_names)]
            tracking_number = _rand_tracking_number(ci * 100 + p)
            contents = random.choice(parcel_contents_options)
            first_name = random.choice(recipient_first_names)
            last_name = random.choice(recipient_last_names)

            created_at = now - timedelta(days=random.randint(1, 20), hours=random.randint(0, 23))

            parcel = Parcel(
                tracking_number=tracking_number,
                client_id=client.id,
                created_by_user_id=creator.id,
                parcel_size=random.choice(["Standard parcel", "Postable parcel or large letter"]),
                delivery_speed=random.choice(["Standard", "Next Day"]),
                parcel_contents=contents,
                parcel_value_gbp=round(random.uniform(1.0, 500.0), 2),
                recipient_first_name=first_name,
                recipient_last_name=last_name,
                recipient_address_line_1=f"{p} {client.client_name} Road",
                recipient_address_line_2=None,
                recipient_address_line_3=None,
                recipient_address_line_4=None,
                recipient_postcode=_rand_postcode(p),
                recipient_country="United Kingdom",
                status="Label Generated",
                created_at=created_at,
                updated_at=created_at,
            )
            db.session.add(parcel)
            db.session.flush()

            # helper to add track events with incremental timestamps
            def add_event(status, location, description, visible, when):
                ev = TrackEvent(
                    parcel_id=parcel.id,
                    event_status=status,
                    event_location=location,
                    event_description=description,
                    visible_to_client=visible,
                    created_at=when,
                )
                db.session.add(ev)

            # First event: Label Generated at client's city
            t0 = created_at
            add_event("Label Generated", base_city, "Label generated at client site.", True, t0)

            # Build timeline depending on scenario
            if scenario == "label_only":
                # no further events
                parcel.updated_at = t0

            elif scenario == "in_transit_visible":
                t1 = t0 + timedelta(hours=6)
                add_event("In Transit", f"National Hub {base_city}", "Parcel entered the network.", True, t1)
                parcel.status = "In Transit"
                parcel.updated_at = t1

            elif scenario == "in_transit_hidden":
                t1 = t0 + timedelta(hours=6)
                add_event("In Transit", f"National Hub {base_city}", "Arrived at hub.", False, t1)
                parcel.status = "In Transit"
                parcel.updated_at = t1

            elif scenario == "hub_depot_du":
                t1 = t0 + timedelta(hours=6)
                add_event("In Transit", f"National Hub {base_city}", "Arrived at national hub.", True, t1)
                t2 = t1 + timedelta(hours=12)
                depot_city = random.choice([c for c in cities if c != base_city])
                add_event("In Transit", f"Depot {depot_city}", "Arrived at depot.", True, t2)
                t3 = t2 + timedelta(hours=6)
                du = f"{depot_city} DU"
                add_event("In Transit", du, "Arrived at delivery unit.", True, t3)
                parcel.status = "In Transit"
                parcel.updated_at = t3

            elif scenario == "out_for_delivery":
                t1 = t0 + timedelta(hours=6)
                add_event("In Transit", f"National Hub {base_city}", "Arrived at hub.", True, t1)
                t2 = t1 + timedelta(hours=12)
                depot_city = random.choice([c for c in cities if c != base_city])
                add_event("In Transit", f"Depot {depot_city}", "Arrived at depot.", True, t2)
                t3 = t2 + timedelta(hours=6)
                add_event("Out for Delivery", depot_city, "Courier out for delivery.", True, t3)
                parcel.status = "Out for Delivery"
                parcel.updated_at = t3

            elif scenario == "delivered":
                # go through network then delivered
                t1 = t0 + timedelta(hours=6)
                add_event("In Transit", f"National Hub {base_city}", "Arrived at hub.", True, t1)
                t2 = t1 + timedelta(hours=12)
                depot_city = random.choice([c for c in cities if c != base_city])
                add_event("In Transit", f"Depot {depot_city}", "Arrived at depot.", True, t2)
                t3 = t2 + timedelta(hours=6)
                add_event("Out for Delivery", depot_city, "Courier out for delivery.", True, t3)
                t4 = t3 + timedelta(hours=4)
                add_event("Delivered", depot_city, "Parcel delivered to recipient.", True, t4)
                parcel.status = "Delivered"
                parcel.updated_at = t4

            elif scenario == "delayed_with_hidden_reason":
                t1 = t0 + timedelta(hours=6)
                add_event("In Transit", f"National Hub {base_city}", "Arrived at hub.", True, t1)
                t2 = t1 + timedelta(hours=10)
                depot_city = random.choice(cities)
                add_event("Delayed", depot_city, "Delay expected: weather disruption.", True, t2)
                # hidden detailed reason
                t3 = t2 + timedelta(hours=1)
                detailed = random.choice(["Courier broken down","Flooding reported","Heavy weather","Cannot access building, will attempt next day"]) 
                add_event("Delayed", depot_city, detailed, False, t3)
                parcel.status = "Delayed"
                parcel.updated_at = t3

            elif scenario == "stop_and_return":
                t1 = t0 + timedelta(hours=6)
                add_event("In Transit", f"National Hub {base_city}", "Arrived at hub.", True, t1)
                t2 = t1 + timedelta(hours=12)
                add_event("Stop and return", f"Depot {random.choice(cities)}", "Stop & return requested.", True, t2)
                parcel.status = "Stop and return"
                parcel.updated_at = t2

            elif scenario == "returned_then_delivered":
                # stop and return then re-process and deliver
                t1 = t0 + timedelta(hours=6)
                add_event("In Transit", f"National Hub {base_city}", "Arrived at hub.", True, t1)
                t2 = t1 + timedelta(hours=10)
                add_event("Stop and return", f"Depot {random.choice(cities)}", "Stop & return processed.", True, t2)
                t3 = t2 + timedelta(days=2)
                add_event("In Transit", f"National Hub {base_city}", "Re-entered network.", True, t3)
                t4 = t3 + timedelta(hours=18)
                add_event("Out for Delivery", base_city, "Courier out for delivery.", True, t4)
                t5 = t4 + timedelta(hours=3)
                add_event("Delivered", base_city, "Parcel delivered after return.", True, t5)
                parcel.status = "Delivered"
                parcel.updated_at = t5

            elif scenario == "cancelled_after_in_transit":
                t1 = t0 + timedelta(hours=6)
                add_event("In Transit", f"National Hub {base_city}", "Arrived at hub.", True, t1)
                t2 = t1 + timedelta(hours=8)
                add_event("Cancelled", f"Depot {random.choice(cities)}", "Cancelled - suspected fraudulent parcel.", False, t2)
                parcel.status = "Cancelled"
                parcel.updated_at = t2

            # small sleep between parcels not needed; proceed to next

    db.session.flush()

    def _create_system_comment(enquiry_id, comment_text, created_at):
        comment = EnquiryComment(
            enquiry_id=enquiry_id,
            user_id=system_user.id,
            comment=comment_text,
            created_at=created_at,
        )
        db.session.add(comment)
        return comment

    def _create_comment(enquiry_id, user_id, comment_text, created_at):
        comment = create_enquiry_comment_object(enquiry_id, user_id, comment_text)
        comment.created_at = created_at
        db.session.add(comment)
        return comment

    scenario_definitions = [
        {
            "name": "new_only",
            "category": "Billing issue",
            "requires_tracking": False,
            "subject": "Billing query",
            "message": "Please can you explain the latest invoice?",
            "initial_status": "New",
            "actions": [],
        },
        {
            "name": "admin_reply_wip",
            "category": "Delivery delay",
            "requires_tracking": True,
            "subject": "Delivery delay report",
            "message": "My parcel has not arrived yet.",
            "initial_status": "New",
            "actions": ["admin_reply"],
        },
        {
            "name": "admin_reply_hold",
            "category": "Parcel not delivered",
            "requires_tracking": True,
            "subject": "Parcel not delivered",
            "message": "I have not received the parcel. Please investigate.",
            "initial_status": "New",
            "actions": ["admin_reply", "put_on_hold"],
        },
        {
            "name": "admin_update_details",
            "category": "Incorrect tracking information",
            "requires_tracking": True,
            "subject": "Wrong tracking reference",
            "message": "The tracking number on my order is wrong.",
            "initial_status": "New",
            "actions": ["admin_update_details"],
        },
        {
            "name": "admin_close",
            "category": "Account issue",
            "requires_tracking": False,
            "subject": "Account access",
            "message": "I cannot access my account.",
            "initial_status": "New",
            "actions": ["admin_close"],
        },
        {
            "name": "client_close",
            "category": "General enquiry",
            "requires_tracking": False,
            "subject": "General question",
            "message": "I just wanted to ask if this is still on track.",
            "initial_status": "New",
            "actions": ["client_close"],
        },
    ]

    # For each client create 6 enquiries with representative workflow states
    for ci, client in enumerate(clients, start=1):
        client_user = client_users[ci-1]
        for scenario_index, scenario in enumerate(scenario_definitions, start=1):
            enquiry_created_at = now - timedelta(days=30 - scenario_index, hours=random.randint(0, 6))
            tracking_number = None
            if scenario["requires_tracking"]:
                tracking_number = _rand_tracking_number(ci * 100 + scenario_index)

            enquiry = create_enquiry_object(
                client_user.id,
                scenario["category"],
                scenario["subject"],
                scenario["message"],
                tracking_number=tracking_number,
            )
            enquiry.created_at = enquiry_created_at
            enquiry.updated_at = enquiry_created_at
            enquiry.status = scenario["initial_status"]
            db.session.add(enquiry)
            db.session.flush()

            _create_system_comment(
                enquiry.id,
                f"Enquiry ENQ{enquiry.id:06d} was created.",
                enquiry_created_at,
            )

            admin_for_comment = random.choice(admin_users)
            comment_time = enquiry_created_at + timedelta(hours=1)

            if "admin_reply" in scenario["actions"]:
                _create_comment(
                    enquiry.id,
                    admin_for_comment.id,
                    "We are looking into this issue and will provide an update shortly.",
                    comment_time,
                )
                if enquiry.status == "New":
                    enquiry.status = "Work in Progress"
                    enquiry.updated_at = comment_time
                    _create_system_comment(
                        enquiry.id,
                        f"{admin_for_comment.display_name} updated the enquiry status from New to Work in Progress.",
                        comment_time + timedelta(minutes=1),
                    )

            if "put_on_hold" in scenario["actions"]:
                update_time = comment_time + timedelta(hours=1)
                old_values = {
                    "category": enquiry.category,
                    "tracking_number": enquiry.tracking_number,
                    "subject": enquiry.subject,
                    "message": enquiry.message,
                    "status": enquiry.status,
                }
                update_enquiry(enquiry, status="On Hold", closed_at=None)
                enquiry.updated_at = update_time
                new_values = {
                    "category": enquiry.category,
                    "tracking_number": enquiry.tracking_number,
                    "subject": enquiry.subject,
                    "message": enquiry.message,
                    "status": enquiry.status,
                }
                change_comment = build_enquiry_change_comment(old_values, new_values, admin_for_comment.display_name)
                if change_comment:
                    _create_system_comment(enquiry.id, change_comment, update_time)

            if "admin_update_details" in scenario["actions"]:
                update_time = comment_time + timedelta(hours=1)
                old_values = {
                    "category": enquiry.category,
                    "tracking_number": enquiry.tracking_number,
                    "subject": enquiry.subject,
                    "message": enquiry.message,
                    "status": enquiry.status,
                }
                update_enquiry(
                    enquiry,
                    category="Address issue",
                    tracking_number=enquiry.tracking_number,
                    subject="Address correction required",
                    message="The address provided on the order is incorrect and needs changing.",
                    status="Work in Progress",
                )
                enquiry.updated_at = update_time
                new_values = {
                    "category": enquiry.category,
                    "tracking_number": enquiry.tracking_number,
                    "subject": enquiry.subject,
                    "message": enquiry.message,
                    "status": enquiry.status,
                }
                change_comment = build_enquiry_change_comment(old_values, new_values, admin_for_comment.display_name)
                if change_comment:
                    _create_system_comment(enquiry.id, change_comment, update_time)
                _create_comment(
                    enquiry.id,
                    admin_for_comment.id,
                    "I have corrected the ticket details and will continue to monitor this issue.",
                    update_time + timedelta(minutes=5),
                )

            if "admin_close" in scenario["actions"]:
                close_time = comment_time + timedelta(hours=2)
                old_values = {
                    "category": enquiry.category,
                    "tracking_number": enquiry.tracking_number,
                    "subject": enquiry.subject,
                    "message": enquiry.message,
                    "status": enquiry.status,
                }
                update_enquiry(enquiry, status="Closed", closed_at=close_time)
                enquiry.updated_at = close_time
                new_values = {
                    "category": enquiry.category,
                    "tracking_number": enquiry.tracking_number,
                    "subject": enquiry.subject,
                    "message": enquiry.message,
                    "status": enquiry.status,
                }
                change_comment = build_enquiry_change_comment(old_values, new_values, admin_for_comment.display_name)
                if change_comment:
                    _create_system_comment(enquiry.id, change_comment, close_time)
                _create_comment(
                    enquiry.id,
                    admin_for_comment.id,
                    "The enquiry has now been resolved and closed. Please reopen if you need further help.",
                    close_time + timedelta(minutes=5),
                )

            if "client_close" in scenario["actions"]:
                close_time = comment_time + timedelta(hours=2)
                update_enquiry(enquiry, status="Closed", closed_at=close_time)
                enquiry.updated_at = close_time
                _create_system_comment(
                    enquiry.id,
                    f"{client_user.display_name} closed the enquiry.",
                    close_time,
                )

            if scenario.get("force_closed"):
                close_time = comment_time + timedelta(hours=1)
                update_enquiry(enquiry, status="Closed", closed_at=close_time)
                enquiry.updated_at = close_time

    db.session.commit()

    print("Database seeded: admins, clients, parcels, track events, enquiries, and comments created.")

