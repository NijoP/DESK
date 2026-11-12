#!/usr/bin/env bash
# Step 5: hardware_design on the scratch project, run by Weft. EXPECTED TO FAIL CLOSED today.
# DESK backs the understand stage and component families, but not component search: the node service answers
# NODE_UNAVAILABLE (HTTP 501) without `outputs`, the node's Cast to its typed envelope cannot succeed, and the run
# must end failed with nothing after it run. What this step proves is that an unavailable stage stops the
# workflow: no BOM approval, no schematic, no live board node, no release.
# Then: a seeded re-run (`weft run --seed=<failed run>`) must reuse the completed nodes and stop at the same place.
source "$(dirname "$0")/common.sh"
need weft; need curl

REQ="${LINUX_DIR}/fixtures/weftval_requirements.json"
curl -fsS "${SERVICE_URL}/health" >/dev/null || die "the DESK node service is not up; run 30_prepare_desk.sh"
trace() { python3 "${LINUX_DIR}/check_trace.py" --projects-root "${VAL_PROJECTS}" --project "${VAL_PROJECT}" "$@"; }
AFTER_BOM=(DeskMPNResolver DeskBOMGenerator DeskSchematicCompiler DeskPlacementPlanner DeskRoutingExecutor DeskQualityGate DeskReleaseGate DeskReleaseGenerator)

say "Fail-closed run"
t0="$(date +%s)"
out="$(desk weft run hardware_design --project "${VAL_PROJECTS}/${VAL_PROJECT}" --requirements "$REQ" --evidence board --service "${SERVICE_URL}")" || true
RUN="$(python3 -c 'import json,sys; print(json.loads(sys.stdin.read()).get("runId") or "")' <<<"$out" 2>/dev/null)"
[[ -n "$RUN" ]] && record hd.start PASS "run ${RUN}" || { record hd.start FAIL "no run id: ${out:0:300}"; exit 1; }
rc="$(weft_wait "$RUN" 10m --waiting-for-input)"
case "$rc" in
  10) record hd.fails_closed PASS "the run ended failed after $(( $(date +%s) - t0 )) s" ;;
  11) record hd.fails_closed FAIL "the run parked on a wait; nothing in the BOM stage should have reached an approval" ;;
  0)  record hd.fails_closed FAIL "the run COMPLETED although component search is unavailable" ;;
  *)  record hd.fails_closed FAIL "weft wait exit ${rc}" ;;
esac
weft logs "$RUN" > "${VAL_LOGS}/hd_run.log" 2>&1 || true
trace --run "$RUN" --called DeskRequirementIntake DeskDesignProfileCompiler DeskComponentFamilyResolver \
      --failed DeskComponentSearch=NODE_UNAVAILABLE --not-called "${AFTER_BOM[@]}" --no-approval > "${VAL_LOGS}/hd_trace.json" \
  && record hd.desk_trace PASS "stopped at DeskComponentSearch (NODE_UNAVAILABLE); nothing after it ran; no approval" \
  || record hd.desk_trace FAIL "see ${VAL_LOGS}/hd_trace.json"

say "Seeded re-run of the failed run"
# `desk weft resume` prints the run's state, then the seeded run it started: the last runId is the new run.
r="$(desk weft resume "$RUN" --reseed hardware_design 2>&1)" || true
RUN2="$(grep -o '"runId": *"[^"]*"' <<<"$r" | tail -1 | sed 's/.*"\([^"]*\)"$/\1/')"
if [[ -n "$RUN2" && "$RUN2" != "$RUN" ]]; then
  rc="$(weft_wait "$RUN2" 10m --waiting-for-input)"
  [[ "$rc" == "10" ]] && record hd.reseed PASS "seeded run ${RUN2} stopped at the same unavailable stage" || record hd.reseed FAIL "seeded run: weft wait exit ${rc}"
  trace --run "$RUN2" --not-called DeskRequirementIntake DeskDesignProfileCompiler "${AFTER_BOM[@]}" > "${VAL_LOGS}/hd_reseed_trace.json" \
    && record hd.reseed_reuse PASS "Weft reused the completed nodes: DESK saw no repeat of the understand stage" \
    || record hd.reseed_reuse FAIL "see ${VAL_LOGS}/hd_reseed_trace.json (a missing trace means DESK was called for nothing, also a FAIL)"
else
  record hd.reseed FAIL "no seeded run id: ${r:0:300}"
fi
say "hardware_design done. Next: 60_full_suite.sh"
