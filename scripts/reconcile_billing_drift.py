"""Nightly Billing Reconciliation Job: Detects and fixes drift between DB events and Stripe Meter submissions."""

import sys
from datetime import datetime, timezone
from pathlib import Path
from sqlalchemy import func

# Console encoding fix
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))

from agent_memory.database import init_db, get_db
from agent_memory.models.db_models import Organization, UsageEvent, StripeMeterSubmission
from agent_memory.billing.metering_worker import metering_worker


def run_reconciliation(auto_heal: bool = True):
    print("\n" + "=" * 78)
    print(f" 🔍 NIGHTLY BILLING RECONCILIATION AUDIT [{datetime.now(timezone.utc).isoformat()}]")
    print("=" * 78)

    init_db()

    total_drift_units = 0
    orgs_with_drift = []

    with get_db() as db:
        orgs = db.query(Organization).all()
        print(f"Scanning {len(orgs)} organizations for usage metering drift...\n")

        for org in orgs:
            rec = metering_worker.run_reconciliation_check(db, org.id)
            usage_units = rec["internal_usage_events_units"]
            meter_units = rec["submitted_meter_units"]
            drift = rec["unmetered_drift"]

            if drift > 0:
                print(f"  ⚠️  DRIFT DETECTED for '{org.name}' ({org.id}):")
                print(f"      Internal Usage : {usage_units:,} units")
                print(f"      Meter Submitted: {meter_units:,} units")
                print(f"      Unmetered Gap  : {drift:,} units")
                total_drift_units += drift
                orgs_with_drift.append(org.id)
            else:
                print(f"  ✓ '{org.name}' ({org.id}): Reconciled ({usage_units:,} units in sync)")

        # Auto-heal / catch up unmetered events if requested
        if auto_heal and total_drift_units > 0:
            print(f"\n⚡ Auto-healing {total_drift_units} unmetered events via MeteringWorker...")
            sync_res = metering_worker.sync_pending_events(db, batch_size=1000)
            print(f"  ✓ Successfully submitted {sync_res.get('synced_count', 0)} backlogged events to Stripe Meter API!")

    print("\n" + "=" * 78)
    if total_drift_units == 0:
        print(" 🏆 RECONCILIATION COMPLETE: ZERO DRIFT DETECTED (100% IN SYNC)")
    else:
        print(f" ⚠️  RECONCILIATION COMPLETE: {len(orgs_with_drift)} orgs had drift; auto-healing applied.")
    print("=" * 78 + "\n")

    return {"total_drift_units": total_drift_units, "orgs_with_drift": orgs_with_drift}


if __name__ == "__main__":
    run_reconciliation(auto_heal=True)
