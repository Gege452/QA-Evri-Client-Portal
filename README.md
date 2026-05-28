# QA-Evri-Client-Portal

A web-based client portal for managing parcels, enquiries, and account information for EVRi courier services. The portal supports two user roles: **Admin** (internal management) and **Client** (customer self-service).

Hosted on: https://qa-evri-client-portal.onrender.com/

---

## Table of Contents

- [Business Overview](#business-overview)
- [Technical Overview](#technical-overview)
  - [Architecture](#architecture)
  - [Database](#database)
  - [Authentication & Authorization](#authentication--authorization)
  - [Dependencies](#dependencies)
- [How to Run the Application Locally](#how-to-run-the-application-locally)
- [Testing](#testing)
- [Security Considerations](#security-considerations)

---

## Design Documentation

- **UI Design**: Refer to the HTML templates in `templates/` directory
- **Database Schema**: Models defined in `models/` directory
  - [Client Model](models/client.py)
  - [User Model](models/user.py)
  - [Parcel Model](models/parcel.py)
  - [Enquiry Model](models/enquiry.py)

---

## Business Overview

The EVRi Client Portal is a customer-facing application that enables courier clients to:

- **Track Parcels**: Monitor parcel delivery status in real-time with tracking events (e.g., "Label Generated", "In Transit", "Delivered")
- **Manage Enquiries**: Submit support enquiries categorized by type (e.g., "Parcel not delivered", "Damaged parcel", "Billing issue")
- **Control Deliveries**: Request "Stop and Return" for parcels still in transit
- **Account Management**: View account details, reset passwords, and manage client information

For **Admins**, the portal provides:
- Full client management (create, view, update client details)
- Enquiry triage and response workflows
- Parcel oversight and status management
- User account administration

---

## Technical Overview

### Architecture

The application is built using **Flask**, a lightweight Python web framework, with a **SQLite** database backend. The application follows a modular blueprint structure:

- **Routes** (`routes/`): Request handlers organized by domain
  - `auth_routes.py`: Login, logout, password reset
  - `admin_routes.py`: Admin dashboard and client management
  - `client_routes.py`: Client self-service endpoints
  - `enquiry_routes.py`: Enquiry CRUD operations
  - `parcel_routes.py`: Parcel tracking and stop/return requests
- **Models** (`models/`): SQLAlchemy ORM definitions for database entities
- **Templates** (`templates/`): Jinja2 HTML templates with CSS styling
- **Static** (`static/`): CSS stylesheets

### Database

**Engine**: SQLite (file-based: `evri_client_portal.db`)

**Core Tables**:
- `user`: User accounts with roles (admin/client), password hashes, and activation status
- `client`: Business client records with contact info, address, and settings
- `parcel`: Parcel shipments with recipient details, size, speed, and status
- `track_event`: Status updates for parcels (e.g., "Label Generated", "In Transit", "Delivered")
- `enquiry`: Support tickets with categories, status, and client association
- `enquiry_comment`: Comments on enquiries for back-and-forth communication

**Key Relationships**:
- User → Client (many users can belong to one client)
- Parcel → Client (parcels belong to a client)
- Parcel → TrackEvent (one parcel has many tracking events)
- Enquiry → User (enquiries created by users)

**Initialization**: Database is auto-created on app startup via `seed.py`, which seeds default admin user and configuration data.

### Authentication & Authorization

- **Session-based**: Flask sessions with secure password hashing (Werkzeug)
- **Role-based Access Control**: Two roles enforced via route decorators
  - `admin`: Access to `/admin/*` endpoints
  - `client`: Access to `/client/*` endpoints
- **Password Requirements**: Enforced via `validators.py`
- **Forced Password Reset**: Clients can be flagged with `must_reset_password=True` to force reset on next login

### Dependencies

| Package | Version | Purpose |
|---------|---------|---------|
| Flask | 3.1.3 | Web framework |
| Flask-SQLAlchemy | 3.1.1 | ORM integration |
| Flask-WTF | 1.2.2 | CSRF protection and form utilities |
| SQLAlchemy | 2.0.35 | Database ORM |
| Werkzeug | 3.1.6 | WSGI utilities, password hashing |
| pytest | >=9.0.3 | Testing framework |
| urllib3 | >=2.7.0 | HTTP client library |
| requests | >=2.33.0 | HTTP library |
| filelock | >=3.20.3 | File locking |

---

## How to Run the Application Locally

### Prerequisites

- **Python 3.12** installed
- **pip** package manager

### Setup Steps

1. **Clone/Navigate to the repository**:
   ```bash
   cd QA-Evri-Client-Portal
   ```

2. **Create a virtual environment** (recommended):
   ```bash
   python -m venv venv
   # On Windows:
   venv\Scripts\activate
   # On macOS/Linux:
   source venv/bin/activate
   ```

3. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

4. **Run the application**:
   ```bash
   python app.py
   ```

5. **Access the portal**:
   - Open browser to `http://localhost:5000`
   - Default login credentials (seeded):
     - **Admin**: `admin@evri.com` / `adminpass`
     - **Client**: `client@example.com` / `clientpass`

6. **Database**:
   - SQLite database is automatically created in `instance/evri_client_portal.db` on first run
   - To reset, delete the database file and restart the app

---

## Testing

### Test Suite

The project includes comprehensive tests in `tests/test_app.py` covering:
- **Authentication**: Login, password validation, forced resets
- **Authorization**: Role-based access control
- **Business Logic**: Parcel creation, enquiry submission, stop & return rules
- **Data Integrity**: Track events, client isolation

### Running Tests Locally

```bash
# Run all tests
pytest tests/test_app.py -v

# Run specific test
pytest tests/test_app.py::test_admin_login_redirects_to_admin_home -v

# Run with coverage
pytest tests/test_app.py --cov=. -v
```

### CI/CD Pipeline

The project includes GitHub Actions workflow (`.github/workflows/test.yml`):
- **Application Tests**: Runs pytest on each push/PR to `main`
- **Security Tests**: OWASP-mapped security validation (runs after app tests pass)
- **Dependency Scan**: pip-audit vulnerability scanning

---

## Security Considerations

### Implemented

- ✅ **Password Hashing**: Werkzeug's secure password hashing for storage
- ✅ **Session Management**: Flask session handling
- ✅ **Role-Based Access**: Route-level authorization checks
- ✅ **SQL Injection Protection**: SQLAlchemy ORM parameterization
- ✅ **CSRF Protection**: Implemented via Flask-WTF CSRFProtect and hidden form tokens
- ✅ **Dependency Management**: Pinned versions with vulnerability scanning

### Recommendations

- 🔧 **HTTPS**: Enable SSL/TLS in production
- 🔧 **CORS**: Configure if exposing APIs to external clients
- 🔧 **Rate Limiting**: Add request rate limiting for login endpoints
- 🔧 **Logging**: Implement audit logging for sensitive operations
- 🔧 **Secrets**: Use environment variables for `SECRET_KEY` and `DATABASE_URI` in production

---

## Key User Journeys

### Admin User
1. Login → Admin Home → Manage Clients → Create Client (multi-step form) → Assign Users → Monitor Parcels/Enquiries

### Client User
1. Login → Client Home → Create Parcel → View Parcels → Request Stop & Return OR Submit Enquiry → Track Status

---

## File Structure Summary

```
QA-Evri-Client-Portal/
├── app.py                    # Flask app factory
├── config.py                 # Application constants & configurations
├── auth_utils.py             # Authentication utilities
├── validators.py             # Input validation functions
├── helpers.py                # Helper functions
├── seed.py                   # Database seeding
├── extensions.py             # SQLAlchemy instance
├── requirements.txt          # Python dependencies
├── models/                   # SQLAlchemy models
├── routes/                   # Flask blueprints (route handlers)
├── templates/                # Jinja2 HTML templates
├── static/                   # CSS, JS, assets
├── tests/                    # Pytest test suite
└── instance/                 # Runtime data (database file)
```

---

## Troubleshooting

| Issue | Solution |
|-------|----------|
| "Database is locked" | Delete `instance/evri_client_portal.db` and restart |
| Tests fail with "module not found" | Run `pip install -r requirements.txt` and ensure venv is activated |
| Port 5000 already in use | Set `PORT` env variable: `PORT=5001 python app.py` |
| Dependency vulnerabilities | Update via `pip install --upgrade` or use constraints file |

---