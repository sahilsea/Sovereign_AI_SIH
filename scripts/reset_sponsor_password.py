"""Reset a compartment sponsor's password at the server console.

Administrators cannot reset sponsor passwords through the application (they
would receive the new password and could act as the sponsor). Recovery is a
deliberate, physical-access operation on the server instead, and it is
written to the audit ledger.

Usage:
  python scripts/reset_sponsor_password.py --id safety-001 --password 'NewPassword123'
"""

import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from auth.sponsors import sponsor_ids
from auth.users import hash_password
from trust.ledger import get_db_connection, log as ledger_log


def main():
    parser = argparse.ArgumentParser(description="Reset a sponsor's password (server console only).")
    parser.add_argument("--id", required=True, help="Sponsor person_id")
    parser.add_argument("--password", required=True, help="New password (min 8 characters)")
    parser.add_argument("--force-change", action="store_true", help="Require a change at next login")
    parser.add_argument("--db-path", default=None)
    args = parser.parse_args()

    if args.id not in sponsor_ids():
        sys.exit(f"ERROR: '{args.id}' is not a compartment sponsor. Admins reset other accounts in the app.")
    if len(args.password) < 8:
        sys.exit("ERROR: password must be at least 8 characters.")

    db_path = args.db_path or os.getenv("SEVERANCE_DB_PATH", "severance.db")
    pwd_hash, salt = hash_password(args.password)
    conn = get_db_connection(db_path)
    try:
        with conn:
            cur = conn.execute(
                "UPDATE users SET password_hash = ?, salt = ?, must_change_password = ? WHERE person_id = ?;",
                (pwd_hash, salt, 1 if args.force_change else 0, args.id),
            )
            if cur.rowcount == 0:
                sys.exit(f"ERROR: account '{args.id}' does not exist.")
    finally:
        conn.close()
    ledger_log(db_path=db_path, actor="server-console", action="RESET_SPONSOR_PASSWORD", details={"subject": args.id})
    print(f"SUCCESS: password reset for sponsor '{args.id}'.")


if __name__ == "__main__":
    main()
