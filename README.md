# Davarna

GitHub-ready export of the current Davarna production codebase.

This export was taken from the live server and cleaned for source control.
It is prepared for a safe first push to a private GitHub repository, with enough structure to be published later after a final review.

## Included

- `backend/` FastAPI backend
- `davarna-bot/` Telegram bot
- `deploy/` Nginx and Certbot deployment assets
- `scripts/` operational scripts
- `database/schema_only.sql` schema-only database backup
- `.env.example` and `.env.prod.example` safe example env files
- `davarna-bot/.env.example` and `davarna-bot/.env.prod.example` safe bot env examples

## Not Included

- real `.env` secrets
- runtime storage and uploaded receipts
- Python virtual environments
- private full database dump
- temporary backup artifacts from the live server

## Private Backup

The full private database dump is stored separately and must not be pushed to GitHub:

- `E:\DAVARNA_DB_PRIVATE_20260228_012302.sql.gz`

## Recommended Release Strategy

### Stage 1: Private Repository (Recommended First)

Use a private repository first to validate:
- no secrets remain
- docs are correct
- compose layout matches your target server
- collaborators only see reviewed code

### Stage 2: Optional Public Repository

Only consider a public release after a second review of:
- branding and private infrastructure details
- any hard-coded private URLs, chat ids, and operational references
- whether deployment docs should be simplified for open-source use

## Publish Flow

1. Review `.env.prod.example` and create a real `.env.prod` for your target server.
2. Review `davarna-bot/.env.example` or `davarna-bot/.env.prod.example`.
3. Review `docker-compose.yml` and `RELEASE_COMPOSE_REVIEW.md`.
4. Push this folder to a private repository first.
5. Re-check GitHub web UI after the first push.

## Compose Notes

- `docker-compose.yml` is production-oriented.
- `backend` expects env from `BACKEND_ENV_FILE`.
- `bot` expects env from `BOT_ENV_FILE`.
- `nginx` is behind the `edge` profile.
- local bind for backend is restricted to `127.0.0.1`.
- runtime storage is expected on the deployment host and is intentionally not bundled here.

## Database Notes

- `database/schema_only.sql` is safe for source control.
- Full live data is intentionally not inside this repository export.
- Do not import `schema_only.sql` over an active production database.

## Files To Read Before Push

- `README.md`
- `PUBLISHING_NOTES.md`
- `PRE_PUSH_CHECKLIST.md`
- `RELEASE_COMPOSE_REVIEW.md`
- `DEPLOYMENT.md`
