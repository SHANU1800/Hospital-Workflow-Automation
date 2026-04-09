"""Initialize schema and seed mock data into the configured Neon database."""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

load_dotenv(PROJECT_ROOT / ".env")

from models.database import init_db
from seed_data import seed_database


def _mask_db_url(url: str) -> str:
    if "@" not in url:
        return url
    prefix, host_part = url.split("@", 1)
    if "://" in prefix:
        scheme, creds = prefix.split("://", 1)
        if ":" in creds:
            user, _ = creds.split(":", 1)
            return f"{scheme}://{user}:***@{host_part}"
    return "***"


async def main() -> None:
    db_url = os.getenv("DATABASE_URL", "")
    print("🔌 Target DB:", _mask_db_url(db_url))
    print("🛠️ Creating/updating tables...")
    await init_db()
    print("🌱 Seeding mock data (idempotent)...")
    await seed_database()
    print("✅ Neon DB seeding complete")


if __name__ == "__main__":
    asyncio.run(main())
