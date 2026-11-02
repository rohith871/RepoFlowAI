# AuthPlatform Service

A decoupled authentication and session verification service designed with clean architecture principles.

## Architecture
- **gateway.py**: REST API endpoints for login and token validation.
- **security.py**: Domain cryptographic logic (passwords, JWT tokens).
- **user_store.py**: Data access and session persistence.
- **models.py**: In-memory domain entities (`UserAccount`, `SessionToken`).
- **schema.sql**: Database table definitions.
