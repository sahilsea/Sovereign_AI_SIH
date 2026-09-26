#!/usr/bin/env bash
# Provision the demo accounts at the SERVER CONSOLE (sponsor accounts can't be
# created or reset by an administrator in the app -- separation of duties).
#
#   bash scripts/setup_demo_accounts.sh               # sponsors + employees
#   bash scripts/setup_demo_accounts.sh --with-grants # ...and pre-grant the demo compartments
#
# Sponsors (one per compartment, none of them admins) get password 12345678
# with no forced change, for the demo. Employees get ChangeMe123! and must
# change it at first login. Re-running is safe: existing accounts are skipped.
set -u
cd "$(dirname "$0")/.."
PY=venv/bin/python
SPONSOR_PW="12345678"
EMPLOYEE_PW="ChangeMe123!"

sponsor() {  # id, title
  $PY scripts/create_employee.py --id "$1" --name "$2" --job-title "$2" --grade H \
      --password "$SPONSOR_PW" --no-force-change 2>&1 | tail -1
}
employee() {  # id, title, grade
  $PY scripts/create_employee.py --id "$1" --name "$2" --job-title "$2" --grade "$3" \
      --password "$EMPLOYEE_PW" 2>&1 | tail -1
}

echo "== Compartment sponsors (password: $SPONSOR_PW)"
sponsor safety-001 "Head of Safety"            # hse
sponsor cvo-001    "Chief Vigilance Officer"   # vigilance
sponsor legal-001  "Company Secretary"         # legal
sponsor comm-001   "GM Commercial"             # commercial
sponsor tech-001   "GM Technical"              # technical

echo "== Employees (password: $EMPLOYEE_PW, change at first login)"
employee eng-001 "Process Engineer" B
employee gm-001  "General Manager" F
employee am-001  "Assistant Manager" A

if [ "${1:-}" = "--with-grants" ]; then
  echo "== Grants, each made by that compartment's own sponsor"
  $PY scripts/grant_compartment.py --actor safety-001 --target eng-001 --compartment hse 2>&1 | tail -1
  $PY scripts/grant_compartment.py --actor cvo-001 --target am-001 --compartment vigilance 2>&1 | tail -1
  $PY scripts/grant_compartment.py --actor comm-001 --target gm-001 --compartment commercial 2>&1 | tail -1
else
  echo "== No grants made. Log in as a sponsor (e.g. safety-001) -> Compartment Access to grant."
fi
