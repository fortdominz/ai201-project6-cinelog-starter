"""
tests/test_watchlist.py — CineLog

Tests for the watchlist service. Fixtures and assertion style mirror
tests/test_collection.py.
"""

import pytest
from app import create_app, db
from models import User, Film, WatchlistEntry
from services.watchlist_service import (
    add_to_watchlist,
    remove_from_watchlist,
    get_watchlist,
    AlreadyInWatchlistError,
    NotInWatchlistError,
)
from services.collection_service import FilmNotFoundError


@pytest.fixture
def app():
    """Isolated test app with an in-memory database."""
    app = create_app(config={
        "TESTING": True,
        "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:",
    })
    with app.app_context():
        db.create_all()
        yield app
        db.session.remove()
        db.drop_all()


@pytest.fixture
def sample_user(app):
    with app.app_context():
        user = User(username="testuser", email="test@example.com")
        db.session.add(user)
        db.session.commit()
        return user.id


@pytest.fixture
def sample_film(app):
    with app.app_context():
        film = Film(title="Paddington 2", year=2017, genre="Comedy")
        db.session.add(film)
        db.session.commit()
        return film.id


# ── Basic add ───────────────────────────────────────────────────────────────

def test_add_to_watchlist_creates_entry(app, sample_user, sample_film):
    """Adding a valid film creates a WatchlistEntry (public by default)."""
    with app.app_context():
        entry = add_to_watchlist(user_id=sample_user, film_id=sample_film)
        assert entry is not None
        assert entry.user_id == sample_user
        assert entry.film_id == sample_film
        assert entry.public is True

        in_db = WatchlistEntry.query.filter_by(
            user_id=sample_user, film_id=sample_film
        ).first()
        assert in_db is not None


# ── Nonexistent film (Comment 3 — required) ──────────────────────────────────

def test_add_to_watchlist_nonexistent_film_raises(app, sample_user):
    """
    Adding a film_id that doesn't exist should raise FilmNotFoundError,
    not a database integrity error. (Equivalent of the collection test.)
    """
    with app.app_context():
        fake_film_id = "00000000-0000-0000-0000-000000000000"
        with pytest.raises(FilmNotFoundError):
            add_to_watchlist(user_id=sample_user, film_id=fake_film_id)


# ── Deduplication (verifies Comment 2) ───────────────────────────────────────

def test_add_to_watchlist_duplicate_raises(app, sample_user, sample_film):
    """Adding the same film twice raises AlreadyInWatchlistError, no duplicate row."""
    with app.app_context():
        add_to_watchlist(user_id=sample_user, film_id=sample_film)
        with pytest.raises(AlreadyInWatchlistError):
            add_to_watchlist(user_id=sample_user, film_id=sample_film)
        count = WatchlistEntry.query.filter_by(
            user_id=sample_user, film_id=sample_film
        ).count()
        assert count == 1


# ── Extra edge case (not requested in review): dedup is per-user ─────────────

def test_same_film_allowed_for_two_different_users(app, sample_film):
    """
    Deduplication is scoped to (user_id, film_id): two different users can each
    have the same film on their watchlist. This guards against a future 'fix'
    that makes the check global.
    """
    with app.app_context():
        u1 = User(username="alice", email="alice@example.com")
        u2 = User(username="bob", email="bob@example.com")
        db.session.add_all([u1, u2])
        db.session.commit()

        add_to_watchlist(user_id=u1.id, film_id=sample_film)
        add_to_watchlist(user_id=u2.id, film_id=sample_film)  # must NOT raise

        assert WatchlistEntry.query.filter_by(film_id=sample_film).count() == 2


# ── Sort order (verifies Comment 5) ──────────────────────────────────────────

def test_get_watchlist_returns_newest_first(app, sample_user):
    """get_watchlist returns entries ordered by date_added descending."""
    with app.app_context():
        from datetime import datetime, timezone, timedelta

        film_a = Film(title="Alien", year=1979, genre="Horror")
        film_b = Film(title="Blade Runner", year=1982, genre="Sci-Fi")
        db.session.add_all([film_a, film_b])
        db.session.commit()

        earlier = datetime.now(timezone.utc) - timedelta(days=5)
        later = datetime.now(timezone.utc)
        db.session.add_all([
            WatchlistEntry(user_id=sample_user, film_id=film_a.id, date_added=earlier),
            WatchlistEntry(user_id=sample_user, film_id=film_b.id, date_added=later),
        ])
        db.session.commit()

        titles = [f["title"] for f in get_watchlist(sample_user)]
        assert titles[0] == "Blade Runner"  # added later → first
        assert titles[1] == "Alien"


# ── Removal (stretch) ────────────────────────────────────────────────────────

def test_remove_from_watchlist_removes_entry(app, sample_user, sample_film):
    with app.app_context():
        add_to_watchlist(user_id=sample_user, film_id=sample_film)
        assert remove_from_watchlist(sample_user, sample_film) is True
        assert WatchlistEntry.query.filter_by(
            user_id=sample_user, film_id=sample_film
        ).first() is None


def test_remove_from_watchlist_not_present_raises(app, sample_user, sample_film):
    with app.app_context():
        with pytest.raises(NotInWatchlistError):
            remove_from_watchlist(sample_user, sample_film)
