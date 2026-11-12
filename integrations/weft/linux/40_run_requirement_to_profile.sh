#!/usr/bin/env bash
# Step 4: requirement_to_profile on the scratch project, run by Weft. Demonstrates, and records with timings:
#   A. a durable run that parks on the human profile approval (weft wait exit 11, node approve.review waiting)
#   B. the parked run surviving a runtime restart (weft daemon stop / start), then resuming on the answer
#   C. an approval answered through Weft's signal API, recorded by DESK bound to the profile hash
#   D. a second run of the same requirements: DESK replays its stored engine results; a rejection is recorded
# Every check reads DESK's own records (check_trace.py), never only Weft's word. The approval subject is a
# validation fixture, not a client design.
source "$(dirname "$0")/common.sh"
need weft; need curl

REQ="${LINUX_DIR}/fixtures/weftval_requirements.json"
UNDERSTAND=(DeskRequirementIntake DeskRequirementValidator DeskDomainClassifier DeskDesignProfileCompiler)
ENGINEERING=(DeskComponentFamilyResolver DeskPowerDistributionAnalyzer)
curl -fsS "${SERVICE_URL}/health" >/dev/null || die "the DESK node service is not up; run 30_prepare_desk.sh"

trace() { python3 "${LINUX_DIR}/check_trace.py" --projects-root "${VAL_PROJECTS}" --project "${VAL_PROJECT}" "$@"; }
now() { date +%s.%N; }
secs() { python3 -c "print(f'{$2 - $1:.1f}')"; }
start_run() { # -> run id on stdout
  local out
  out="$(desk weft run requirement_to_profile --project "${VAL_PROJECTS}/${VAL_PROJECT}" --requirements "$REQ" --service "${SERVICE_URL}")" || true
  python3 -c 'import json,sys; d=json.loads(sys.stdin.read()); print(d.get("runId") or "")' <<<"$out" 2>/dev/null
}

say "Signal token for answering approvals (scoped to the project's run tag, 12 h)"
sigfile="${VAL_SECRETS}/signal_token.json"
if [[ ! -s "$sigfile" ]]; then
  (umask 077; weft --json token mint --name desk-validation --tags "${VAL_PROJECT}" --expires 12h > "$sigfile") \
    || { record signal.mint FAIL "weft token mint failed"; exit 1; }
fi
export DESK_WEFT_SIGNAL_TOKEN="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["token"])' "$sigfile")"
record signal.mint PASS "token id $(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["id"])' "$sigfile")"

say "A. Durable run, parked on the profile approval"
t0="$(now)"
RUN_A="$(start_run)"
[[ -n "$RUN_A" ]] && record r2p.start PASS "run ${RUN_A}" || { record r2p.start FAIL "desk weft run gave no run id"; exit 1; }
rc="$(weft_wait "$RUN_A" 10m --waiting-for-input)"; t1="$(now)"
[[ "$rc" == "11" ]] && record r2p.parked PASS "waiting for input after $(secs "$t0" "$t1") s" \
  || { record r2p.parked FAIL "weft wait exit ${rc} (0 done, 10 failed, 12 still running)"; weft logs "$RUN_A" > "${VAL_LOGS}/r2p_A.log" 2>&1 || true; exit 1; }
state="$(weft node-state "$RUN_A" approve.review 2>&1 || true)"
grep -qi "waiting" <<<"$state" && record r2p.node_state PASS "approve.review: $(head -1 <<<"$state")" || record r2p.node_state FAIL "approve.review: $(head -1 <<<"$state")"
trace --run "$RUN_A" --called "${UNDERSTAND[@]}" "${ENGINEERING[@]}" --not-called DeskApprovalRecorder --no-approval > "${VAL_LOGS}/r2p_A_parked.json" \
  && record r2p.desk_before_approval PASS "6 DESK engines ran, no approval recorded" || { record r2p.desk_before_approval FAIL "see ${VAL_LOGS}/r2p_A_parked.json"; exit 1; }

say "B. The parked run survives a runtime restart"
t2="$(now)"
weft daemon stop >"${VAL_LOGS}/daemon_stop.log" 2>&1 || true
weft daemon start >"${VAL_LOGS}/daemon_start.log" 2>&1 || { record r2p.restart FAIL "weft daemon start failed; see ${VAL_LOGS}/daemon_start.log"; exit 1; }
for _ in $(seq 1 60); do weft daemon status 2>/dev/null | grep -q "running at" && break; sleep 2; done
t3="$(now)"
rc="$(weft_wait "$RUN_A" 2m --waiting-for-input)"
[[ "$rc" == "11" ]] && record r2p.survives_restart PASS "runtime back in $(secs "$t2" "$t3") s; the run is still parked" \
  || { record r2p.survives_restart FAIL "after the restart weft wait exit ${rc}"; exit 1; }

say "C. Approve through Weft's signal API; the run resumes and DESK records the decision"
desk weft signals > "${VAL_LOGS}/signals_A.txt" || true
t4="$(now)"
desk weft answer approve.review approve > "${VAL_LOGS}/answer_A.json" \
  && record r2p.answer PASS "approve sent to approve.review" || { record r2p.answer FAIL "see ${VAL_LOGS}/answer_A.json and signals_A.txt"; exit 1; }
rc="$(weft_wait "$RUN_A" 10m)"; t5="$(now)"
[[ "$rc" == "0" ]] && record r2p.completed PASS "completed $(secs "$t4" "$t5") s after the answer" \
  || { record r2p.completed FAIL "weft wait exit ${rc}"; weft logs "$RUN_A" > "${VAL_LOGS}/r2p_A.log" 2>&1 || true; exit 1; }
trace --run "$RUN_A" --called DeskApprovalRecorder --approval profile=approved --all-passed > "${VAL_LOGS}/r2p_A_done.json" \
  && record r2p.desk_after_approval PASS "profile approval recorded by DESK, every DESK call passed" \
  || { record r2p.desk_after_approval FAIL "see ${VAL_LOGS}/r2p_A_done.json"; exit 1; }

say "D. Same requirements again: DESK replays its engines; a rejection is recorded and stops nothing silently"
RUN_B="$(start_run)"
[[ -n "$RUN_B" ]] || { record r2p.rerun FAIL "no run id"; exit 1; }
rc="$(weft_wait "$RUN_B" 10m --waiting-for-input)"
[[ "$rc" == "11" ]] || { record r2p.rerun FAIL "second run: weft wait exit ${rc}"; exit 1; }
trace --run "$RUN_B" --replayed "${UNDERSTAND[@]}" "${ENGINEERING[@]}" > "${VAL_LOGS}/r2p_B_parked.json" \
  && record r2p.idempotent_replay PASS "the second run reused DESK's stored results for all 6 engines" \
  || record r2p.idempotent_replay FAIL "see ${VAL_LOGS}/r2p_B_parked.json"
desk weft answer approve.review reject > "${VAL_LOGS}/answer_B.json" || { record r2p.reject FAIL "see ${VAL_LOGS}/answer_B.json"; exit 1; }
rc="$(weft_wait "$RUN_B" 10m)"
trace --run "$RUN_B" --approval profile=rejected > "${VAL_LOGS}/r2p_B_done.json" \
  && record r2p.reject PASS "rejection recorded by DESK (weft wait exit ${rc})" || record r2p.reject FAIL "see ${VAL_LOGS}/r2p_B_done.json"

say "Weft's own record of the runs"
weft --json runs --tag "${VAL_PROJECT}" --limit 10 > "${VAL_LOGS}/weft_runs.json" 2>&1 || true
info "saved to ${VAL_LOGS}/weft_runs.json"
say "requirement_to_profile done. Next: 50_run_hardware_design.sh"
