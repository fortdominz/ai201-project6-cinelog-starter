# PR Response Doc — CineLog Watchlist Feature

Branch: `feature/watchlist` → `main` · Author: @fortdominz · Reviewer: @dev-lead

---

## AI Usage

I used an AI assistant during this project, and verified everything against the actual code:

- **Orientation.** I had it summarise `models.py`, `services/collection_service.py`, and `tests/test_collection.py` and trace how `add_to_collection()` handles deduplication (query for an existing `(user_id, film_id)` row, raise `AlreadyInCollectionError`). I confirmed each summary by reading the code before relying on it.
- **Rebase diagnosis.** When `git rebase origin/main` reported success but the tests then failed, AI helped me realise the auto-merge had silently dropped my `WatchlistEntry` model and that my `film_id` was still `Integer` against the new UUID `Film.id` — a *semantic* conflict with no conflict markers (see Comment 6).
- **Design decisions (Comments 4 & 5).** I wrote my positions first, then used AI as a devil's advocate ("what counterargument would a reviewer raise?"). For Comment 4 it pushed me to acknowledge the privacy/oversharing tradeoff more directly, which I added. The reasoning below is my own, grounded in CineLog's specific context (its social purpose, and the existing `get_collection` behaviour); AI did not make the decision.
- **Commit hygiene.** I asked it to sanity-check my `git log --oneline` against the conventional-commits spec, then verified against the spec myself.

---

## Comment 1 — Rename `save_to_watchlist` → `add_to_watchlist`
**What I did:** Renamed the function in `services/watchlist_service.py` and updated the one call site in `routes/watchlist/watchlist.py` (both the import and the call). Commit `fix: rename save_to_watchlist to add_to_watchlist per naming convention`.
**How I verified:** Project-wide `grep -rn "save_to_watchlist" --include=*.py .` returns nothing; the route still imports and the app boots. The name now matches the project's `verb_to_noun` convention (cf. `add_to_collection`).

## Comment 2 — Deduplication
**What I did:** Added an `AlreadyInWatchlistError` class and, in `add_to_watchlist()`, a check for an existing `(user_id, film_id)` entry that raises it before inserting — the exact shape used by `add_to_collection()` / `AlreadyInCollectionError`. Commit `fix: raise AlreadyInWatchlistError on duplicate watchlist entries`. I also updated the `/add` endpoint to return **409** for this error instead of a 500.
**How I verified:** `test_add_to_watchlist_duplicate_raises` adds the same film twice, asserts the error is raised, and asserts only one row exists. I modelled the check on `add_to_collection` in `services/collection_service.py`.

## Comment 3 — Missing test
**What I did:** Created `tests/test_watchlist.py`, modelled on `tests/test_collection.py`. The required test — `test_add_to_watchlist_nonexistent_film_raises` — is the direct equivalent of `test_add_to_collection_nonexistent_film_raises`: it passes a UUID that isn't in the DB and asserts `FilmNotFoundError`. Commit `test: add watchlist tests ...`.
**How I verified:** `pytest tests/ -v` → **11 passed** (4 collection + 7 watchlist). I reused the same `app` / `sample_user` / `sample_film` fixtures and `pytest.raises` assertion style as the collection tests.

## Comment 4 — Default visibility (`public=True`)
Default Setting: public=True (with an explicit public flag to override).

Why: CineLog is built for social movie sharing, so the experience works best when friends can see what you want to watch, suggest films, and plan watch-alongs. Setting the default to public keeps that loop going. If visibility were opt-in, most watchlists would stay private just by inertia, which hurts the core app experience.

Tradeoff & Solution: Sharing what you plan to watch can sometimes feel like oversharing if you want to keep a movie to yourself. To handle this, I added an explicit public parameter so you can easily pass public=false on any entry. If usage data down the line shows people constantly setting items to private, I will revisit the default.

## Comment 5 — Sort order
I'm switching the watchlist ordering to date added, newest first.

Right now, get_collection() already uses date_added.desc(), so sorting the watchlist alphabetically just creates an odd inconsistency between two primary lists. A watchlist is ultimately a queue of current interest. The film added five minutes ago is far more relevant than one added six months ago, and alphabetical sorting works against that usage pattern by scattering new adds everywhere.

Instead of adding a configurable sort parameter right now, I'm sticking to a sensible default that aligns with the rest of the app. This also allows dropping the Film join so both queries run on the exact same pattern.

## Comment 6 — Rebase onto UUID `main`
**What conflicted:** `main` merged `refactor: migrate film IDs from integer to UUID`, changing `Film.id` (and `CollectionEntry.film_id`) from `Integer` to `String(36)`. My branch added a `WatchlistEntry` whose `film_id` was still `Integer`.
**How I resolved it:** I ran `git fetch origin` and `git rebase origin/main`. Git reported the rebase succeeded with **no textual conflict markers** — but the auto-merge silently dropped my `WatchlistEntry` model from `models.py`, and the surviving watchlist code still referenced integer IDs. That's a *semantic* conflict git can't flag. I resolved it by rebuilding the branch on top of the UUID `main` with `WatchlistEntry.film_id = db.Column(db.String(36), db.ForeignKey("film.id"))` matching the refactored `Film.id`, and updated the integer references in the service docstrings and the `/add` route body (`film_id: <uuid>`).
**How I verified no conflict remains:** `git log --oneline origin/main..HEAD` shows a linear history with **no merge commits**; `git status` is clean; and `pytest tests/` passes (11/11), including watchlist tests that create and query real UUID `Film` rows.

---

## Stretch features
- **`remove_from_watchlist(user_id, film_id)`** — added following `remove_from_collection` (looks up the entry, deletes it, raises `NotInWatchlistError` if absent). Tested by `test_remove_from_watchlist_removes_entry` and `test_remove_from_watchlist_not_present_raises`.
- **Second (unrequested) test** — `test_same_film_allowed_for_two_different_users`. I chose this edge case because deduplication is scoped to `(user_id, film_id)`, and it's an easy invariant for a future change to break (someone could "simplify" the check to be global). The test locks in that two different users can each watchlist the same film.
- **Visibility toggle** — `add_to_watchlist()` and `POST /watchlist/<user_id>/add` accept an optional `public` flag (default `True`), so callers can set visibility explicitly (directly supports the Comment 4 decision).

---

## Commit history (screenshot)

<!-- Paste your `git log --oneline` screenshot here -->

```
fix: return 404/409 for watchlist add errors instead of 500
test: add watchlist tests for missing film, duplicates, ordering, and removal
feat: add remove_from_watchlist following collection service pattern
feat: support explicit public visibility when adding to watchlist
fix: order watchlist by date added, newest first
fix: raise AlreadyInWatchlistError on duplicate watchlist entries
fix: rename save_to_watchlist to add_to_watchlist per naming convention
feat: add watchlist model, service, and API endpoints
```
Conventional commits, one logical change each, rebased on `main`, no merge commits.

---

## PR Description

**What this adds.** A **watchlist** feature — films a user wants to watch later — alongside the existing collection feature. It ships a `WatchlistEntry` model, a `watchlist_service` (`add_to_watchlist`, `remove_from_watchlist`, `get_watchlist`), and REST endpoints `GET /watchlist/<user_id>` and `POST /watchlist/<user_id>/add`. Adding a film deduplicates per user, the list is returned newest-first, and entries are public by default with an optional per-entry `public` override.

**Design decisions.**
1. **Default visibility = `public=True`** (with an explicit `public` override) — optimising for CineLog's social discovery, with the oversharing tradeoff acknowledged (see Comment 4).
2. **Sort order = date added, newest first** — matching `get_collection` and treating the watchlist as a recency-ordered queue of intent (see Comment 5).

**How to test it manually.**
```bash
# 1) create a user + film, note their UUIDs
FLASK_APP=app:create_app flask shell
>>> from app import db
>>> from models import User, Film
>>> u = User(username="ada", email="ada@example.com")
>>> f = Film(title="Arrival", year=2016, genre="Sci-Fi")
>>> db.session.add_all([u, f]); db.session.commit()
>>> print(u.id, f.id)   # copy these
>>> exit()

# 2) run the app
python app.py           # serves http://127.0.0.1:5000

# 3) add the film to the watchlist  -> 201, {"public": true, ...}
curl -X POST http://127.0.0.1:5000/watchlist/<USER_ID>/add \
  -H "Content-Type: application/json" -d '{"film_id":"<FILM_ID>"}'

# 4) add it again  -> 409 (deduplication)
# 5) add privately: -d '{"film_id":"<FILM_ID>","public":false}'  -> {"public": false}
# 6) view the watchlist (newest first)
curl http://127.0.0.1:5000/watchlist/<USER_ID>

# 7) unknown film  -> 404
curl -X POST http://127.0.0.1:5000/watchlist/<USER_ID>/add \
  -H "Content-Type: application/json" -d '{"film_id":"no-such-id"}'
```
Automated coverage: `pytest tests/ -v` (11 passing).
