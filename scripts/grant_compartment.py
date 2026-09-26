"""CLI utility to grant a compartment directly against the local database,
bypassing the running API/browser session -- enforces the exact same rules
as the live grant endpoint (auth/sponsors.py): the actor must be the
compartment's designated sponsor, cannot grant to themselves, and cannot
grant to an administrator. There is no delegation.

Usage:
  python scripts/grant_compartment.py --actor cvo-001 --target am-001 --compartment vigilance
"""

import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from auth.sponsors import grant_compartment, init_grants_tables
from contracts import Compartment


def main():
    parser = argparse.ArgumentParser(description="Grant a compartment as its sponsor.")
    parser.add_argument("--actor", required=True, help="person_id of the compartment's sponsor")
    parser.add_argument("--compartment", required=True, choices=[c.value for c in Compartment])
    parser.add_argument("--target", required=True, help="person_id to grant the compartment to")
    parser.add_argument("--db-path", default=None)

    args = parser.parse_args()
    db_path = args.db_path or os.getenv("SEVERANCE_DB_PATH", "severance.db")
    comp = Compartment(args.compartment)
    init_grants_tables(db_path)

    try:
        grant_compartment(db_path, actor_id=args.actor, target_id=args.target, compartment=comp)
        print(f"SUCCESS: '{args.actor}' granted '{comp.value}' to '{args.target}'.")
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
