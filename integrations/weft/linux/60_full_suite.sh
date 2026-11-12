#!/usr/bin/env bash
# Step 6: DESK's full test suite on this Linux machine, with a Weft runtime present (so the Weft tests that need a
# compiler or runtime run instead of skipping). Records counts exactly as unittest reports them.
source "$(dirname "$0")/common.sh"

say "Full DESK test suite"
log="${VAL_LOGS}/full_suite.log"
# The model-provider variables change three orchestrator tests' expectations; they are cleared for the suite only.
rc=0
(cd "${DESK_REPO}" && env -u DESK_L1_MODEL_PI -u DESK_L2_MODEL_PI -u DESK_L3_MODEL_PI -u DESK_FRONTIER_PROVIDER -u DESK_FRONTIER_MODEL \
   python3 -m unittest discover -s tests -p "test_*.py") >"$log" 2>&1 || rc=$?
summary="$(grep -E '^Ran [0-9]+ tests' "$log" | tail -1) $(tail -1 "$log")"
if [[ $rc -eq 0 ]]; then
  record suite.full PASS "$summary"
else
  record suite.full FAIL "$summary (see ${log})"
fi
info "skips are listed in ${log}; a skip is acceptable only for a live-only check (EasyEDA, live provider)"
grep -q "routing_orchestrator" "$log" && warn "the routing-engine test needs a Freerouting jar (library/tools/ or FREEROUTING_JAR) and Java 25 (DESK_JAVA)"
exit $rc
