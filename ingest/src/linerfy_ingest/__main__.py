"""CLI: apply the catalog migration and seed the fixture album into Supabase.

By default this is non-destructive: it only runs migrations (idempotently) and
seeds rows. Pass ``--reset`` to first drop the catalog tables; reset is refused
unless the target is a marked local/test database (see ``db.reset``).
"""

from __future__ import annotations

import sys
from pathlib import Path

from .adapter import FixtureSourceAdapter
from .db import apply_migration, connect, reset, seed, verify

_FIXTURE = Path(__file__).resolve().parents[2] / "fixtures" / "reviews.json"


def main() -> None:
    context = FixtureSourceAdapter(_FIXTURE).fetch()
    with connect() as conn:
        if "--reset" in sys.argv[1:]:
            reset(conn)
        apply_migration(conn)
        inserted = seed(conn, context)
    print(f"applied migration; inserted {inserted} rows for {context.release.title}")
    print(verify())


if __name__ == "__main__":
    main()
