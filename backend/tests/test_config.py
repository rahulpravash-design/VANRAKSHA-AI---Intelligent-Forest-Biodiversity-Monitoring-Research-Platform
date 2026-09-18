"""Settings parsing that only ever breaks in a real deployment.

Both behaviours here are driven by how hosting platforms hand over
configuration: a driverless Postgres URL, and a comma-separated origin list.
Neither is exercised by the rest of the suite, which runs on SQLite.
"""

from __future__ import annotations

import pytest
from app.core.config import Settings
from sqlalchemy.engine import make_url


def settings_with(**overrides) -> Settings:
    # _env_file=None so a developer's local .env cannot influence the result.
    return Settings(_env_file=None, **overrides)


@pytest.mark.parametrize("scheme", ["postgres", "postgresql"])
def test_driverless_postgres_url_is_pinned_to_psycopg3(scheme: str) -> None:
    url = settings_with(database_url=f"{scheme}://user:pw@db.example.com:5432/vanraksha").database_url
    assert url == "postgresql+psycopg://user:pw@db.example.com:5432/vanraksha"


@pytest.mark.parametrize("scheme", ["postgres", "postgresql"])
def test_pinned_url_resolves_to_the_installed_driver(scheme: str) -> None:
    """The point of the rewrite: SQLAlchemy must not pick psycopg2."""
    url = make_url(settings_with(database_url=f"{scheme}://u:p@h/db").database_url)
    assert (url.get_backend_name(), url.get_driver_name()) == ("postgresql", "psycopg")


@pytest.mark.parametrize(
    "url",
    [
        "postgresql+psycopg://u:p@h/db",
        "postgresql+psycopg2://u:p@h/db",
        "sqlite:///./vanraksha.db",
        "sqlite:////tmp/absolute.db",
    ],
)
def test_explicit_driver_and_sqlite_are_left_alone(url: str) -> None:
    assert settings_with(database_url=url).database_url == url


def test_only_the_scheme_prefix_is_rewritten() -> None:
    """A credential containing the scheme substring must survive intact."""
    url = settings_with(database_url="postgresql://u:postgres://x@h/db").database_url
    assert url == "postgresql+psycopg://u:postgres://x@h/db"


def test_cors_origins_accepts_a_comma_separated_list() -> None:
    """The form render.yaml and most dashboards use — not valid JSON."""
    origins = settings_with(
        cors_origins="https://a.vercel.app, https://b.vercel.app"
    ).cors_origins
    assert origins == ["https://a.vercel.app", "https://b.vercel.app"]


def test_production_flags_placeholder_secrets() -> None:
    problems = settings_with(
        vanraksha_env="production",
        debug=False,
        jwt_secret="change-me",
        bootstrap_admin_password="change-me-immediately",
    ).warn_insecure()
    assert any("JWT_SECRET" in p for p in problems)
    assert any("BOOTSTRAP_ADMIN_PASSWORD" in p for p in problems)
