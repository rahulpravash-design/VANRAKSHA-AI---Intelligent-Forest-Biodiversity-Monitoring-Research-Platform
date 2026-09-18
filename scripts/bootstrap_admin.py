#!/usr/bin/env python3
"""Create or update the one administrator account, from the environment.

This is the production counterpart to ``scripts/seed.py``: it touches nothing
but a single ADMIN row, driven by ``BOOTSTRAP_ADMIN_EMAIL`` /
``BOOTSTRAP_ADMIN_PASSWORD`` / ``BOOTSTRAP_ADMIN_NAME`` (see ``.env.example``).
Run it once against a freshly migrated, otherwise-empty database — the demo
species catalogue, zones and synthetic observations that ``seed.py`` also
creates belong in a development or demo environment, not in production.

Idempotent: running it again updates the existing account's name and password
rather than creating a duplicate, so it is safe to include in a deployment's
first-boot steps.

Usage::

    python scripts/bootstrap_admin.py
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = REPO_ROOT / "backend"
for path in (str(REPO_ROOT), str(BACKEND_ROOT)):
    if path not in sys.path:
        sys.path.insert(0, path)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)-8s %(message)s")
logger = logging.getLogger("bootstrap_admin")


def main() -> int:
    import app.models  # noqa: F401 - registers every table
    from app.core.config import settings
    from app.core.security import hash_password, validate_password_strength
    from app.db.base import Base
    from app.db.session import engine
    from app.models import User, UserRole
    from sqlalchemy import select
    from sqlalchemy.orm import Session

    if settings.bootstrap_admin_password == "change-me-immediately":
        logger.error(
            "BOOTSTRAP_ADMIN_PASSWORD is still the placeholder value. Set a real "
            "password in the environment before running this script."
        )
        return 2
    problems = validate_password_strength(settings.bootstrap_admin_password)
    if problems:
        logger.error("BOOTSTRAP_ADMIN_PASSWORD is too weak: %s", "; ".join(problems))
        return 2

    Base.metadata.create_all(engine)
    email = settings.bootstrap_admin_email.strip().lower()

    with Session(engine) as db:
        existing = db.execute(select(User).where(User.email == email)).scalar_one_or_none()
        if existing is None:
            user = User(
                full_name=settings.bootstrap_admin_name,
                email=email,
                password_hash=hash_password(settings.bootstrap_admin_password),
                role=UserRole.ADMIN,
                is_active=True,
            )
            db.add(user)
            db.commit()
            logger.info("created administrator account: %s", email)
        else:
            existing.full_name = settings.bootstrap_admin_name
            existing.password_hash = hash_password(settings.bootstrap_admin_password)
            existing.role = UserRole.ADMIN
            existing.is_active = True
            db.commit()
            logger.info("updated existing administrator account: %s", email)

    logger.info(
        "sign in at POST %s/auth/login with the configured BOOTSTRAP_ADMIN_PASSWORD, "
        "then change it via POST /auth/change-password.",
        settings.api_v1_prefix,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
