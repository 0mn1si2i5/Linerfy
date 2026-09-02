"""CLI: apply the catalog migration and seed the fixture album into Supabase."""

from __future__ import annotations

from pathlib import Path

from .adapter import FixtureSourceAdapter
from .db import apply_migration, connect, reset, seed, verify

_FIXTURE = Path(__file__).resolve().parents[2] / "fixtures" / "reviews.json"


def main() -> None:
    context = FixtureSourceAdapter(_FIXTURE).fetch()
    with connect() as conn:
        reset(conn)
        apply_migration(conn)
        inserted = seed(conn, context)
    print(f"applied migration; inserted {inserted} rows for {context.release.title}")
    print(verify())


if __name__ == "__main__":
    main()
