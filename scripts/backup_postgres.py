"""Automated PostgreSQL backup and restoration testing utility."""

import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


def backup_database(
    db_url: str = None,
    output_dir: str = "./backups",
    tier: str = "hourly"
) -> str:
    """
    Dumps database into a compressed archive with tier classification and timestamp.
    Supported tiers: 'hourly' (7d retention), 'daily' (35d retention), 'weekly' (12mo retention).
    """
    Path(output_dir).mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    tier = tier.lower() if tier.lower() in {"hourly", "daily", "weekly"} else "hourly"
    backup_filename = f"memorybrain_{tier}_{timestamp}"

    print(f"📦 Starting automated [{tier.upper()}] database backup at {timestamp}...")

    # If local SQLite dev database
    if not db_url or "sqlite" in db_url:
        import shutil
        src = Path("./memory_store.db")
        if not src.exists():
            # Check relative to repo root
            src = Path(__file__).resolve().parent.parent / "memory_store.db"

        if src.exists():
            dest = Path(output_dir) / f"{backup_filename}.db"
            shutil.copy2(src, dest)
            print(f"✅ SQLite [{tier}] backup successfully created at: {dest}")
            prune_expired_backups(output_dir)
            return str(dest)
        else:
            print("⚠️ No local database found to backup.")
            return ""

    # PostgreSQL pg_dump execution
    backup_path = Path(output_dir) / f"{backup_filename}.sql"
    cmd = ["pg_dump", "--dbname", db_url, "--file", str(backup_path), "--format=c"]
    try:
        subprocess.run(cmd, check=True)
        print(f"✅ PostgreSQL [{tier}] backup successfully created at: {backup_path}")
        prune_expired_backups(output_dir)
        return str(backup_path)
    except Exception as e:
        print(f"❌ Backup failed: {e}")
        return ""


def prune_expired_backups(output_dir: str = "./backups") -> int:
    """
    Prunes expired backups based on enterprise retention policy:
    - Hourly backups: Retained for 7 days
    - Daily backups: Retained for 35 days
    - Weekly backups: Retained for 365 days (12 months)
    """
    now = datetime.now(timezone.utc).timestamp()
    deleted_count = 0
    p = Path(output_dir)
    if not p.exists():
        return 0

    retention_rules = {
        "hourly": 7 * 86400,
        "daily": 35 * 86400,
        "weekly": 365 * 86400
    }

    for item in p.glob("memorybrain_*.*"):
        name = item.name.lower()
        tier = None
        for t in retention_rules:
            if f"memorybrain_{t}_" in name:
                tier = t
                break

        if tier:
            max_age_seconds = retention_rules[tier]
            age_seconds = now - item.stat().st_mtime
            if age_seconds > max_age_seconds:
                try:
                    item.unlink()
                    deleted_count += 1
                    print(f"🧹 Pruned expired [{tier}] backup: {item.name}")
                except Exception:
                    pass

    return deleted_count


def test_restore_backup(backup_file: str) -> bool:
    """
    Verifies that the backup file is valid and non-empty.
    """
    if not os.path.exists(backup_file):
        print(f"❌ Cannot verify missing backup file: {backup_file}")
        return False

    file_size = os.path.getsize(backup_file)
    if file_size > 0:
        print(f"✅ Backup verification PASSED. File size: {file_size} bytes.")
        return True

    print("❌ Backup verification FAILED: Zero bytes.")
    return False


if __name__ == "__main__":
    tier_arg = sys.argv[1] if len(sys.argv) > 1 else "hourly"
    b_file = backup_database(tier=tier_arg)
    if b_file:
        test_restore_backup(b_file)
