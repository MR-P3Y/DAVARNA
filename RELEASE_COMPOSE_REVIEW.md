# Release Compose Review

This file documents the current `docker-compose.yml` from the GitHub-ready export.

## Current Assessment

The compose file is suitable for a private production-oriented repository.
It is not a generic open-source demo compose file, and that is acceptable for a private code release.

## What Is Good

- `mysql`, `redis`, `backend`, and `bot` are separated cleanly.
- `mysql`, `redis`, and the bot are not exposed publicly.
- `backend` is bound to `127.0.0.1`, which keeps it behind a reverse proxy.
- `nginx` is isolated behind the `edge` profile.
- memory limits are defined.
- log rotation is defined with `json-file` caps.
- `restart: unless-stopped` is already in place.
- `TZ=Asia/Tehran` is applied consistently.

## What To Keep In Mind

- This compose file expects real env files that are not included in this export.
- `./storage` and `./davarna-bot/storage` must exist or be created on the target server.
- `deploy/certbot/conf` and `deploy/certbot/www` are deployment assets, not live certificates in this export.
- `container_name` values are fixed; that is fine for a single-host deployment but not ideal for horizontal scaling.

## For Private Repository Use

No structural change is required before a private GitHub push.
The file accurately reflects the current deployment model.

## For Public Open-Source Use

If you later want a cleaner public release, consider these optional changes in a separate branch:

1. Replace production `container_name` values with defaults.
2. Provide a simplified `docker-compose.example.yml` for local development.
3. Move server-specific port defaults into clearer examples.
4. Add a short local-development note for running without host nginx.

## Current Recommendation

Keep the existing `docker-compose.yml` as-is in this export.
It matches the deployed architecture and does not expose secrets by itself.
