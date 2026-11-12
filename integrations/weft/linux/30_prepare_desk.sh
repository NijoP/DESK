#!/usr/bin/env bash
# Step 3: prepare DESK against the running Weft. Touches only DESK's build folder, the validation folder and this
# Weft install's stored connections and picks.
#   1. build the compiler harness from the pinned checkout (it lists the nodes the connection must be picked for)
#   2. compile-check both workflows with `weft validate`, and judge their runs with `weft run --check`
#   3. create the scratch project and start the DESK node service on loopback with its own token
#   4. store the node-service token in Weft ONCE (`weft connect --door own`, header Authorization) and pick it for
#      every DESK HttpRequest of both workflows (`weft connect <node> --grant <id>`): a pick is per node, per
#      include site, kept by the install (docs/src/build/connections.md at the pin)
source "$(dirname "$0")/common.sh"
need weft; need cargo

say "Compiler harness"
if desk weft build-validator --checkout "${WEFT_DIR}" >"${VAL_LOGS}/harness.log" 2>&1; then
  record desk.harness PASS "built against ${WEFT_DIR}"
else
  record desk.harness FAIL "see ${VAL_LOGS}/harness.log"; exit 1
fi

say "Compile and admission checks"
desk weft gen --check >/dev/null && record desk.node_files PASS "generated node files match the contracts" || { record desk.node_files FAIL "run desk.py weft gen"; exit 1; }
for wf in requirement_to_profile hardware_design; do
  out="$(desk weft validate "$wf" --json || true)"
  verdict="$(python3 -c 'import json,sys; r=json.loads(sys.stdin.read())[0]; print(r["validator"], r["ok"], len(r["errors"]), len(r["warnings"]))' <<<"$out" 2>/dev/null || echo "? False ? ?")"
  read -r validator ok errs warns <<<"$verdict"
  [[ "$ok" == "True" && "$warns" == "0" ]] && record "validate.$wf" PASS "$validator: 0 errors, 0 warnings" \
    || { record "validate.$wf" FAIL "$validator: ${errs} error(s), ${warns} warning(s)"; echo "$out" > "${VAL_LOGS}/validate.$wf.json"; exit 1; }
  if desk weft check-run "$wf" --project "${VAL_PROJECT}" >"${VAL_LOGS}/check-run.$wf.log" 2>&1; then
    record "check_run.$wf" PASS "$(head -1 "${VAL_LOGS}/check-run.$wf.log")"
  else
    record "check_run.$wf" FAIL "see ${VAL_LOGS}/check-run.$wf.log"; exit 1
  fi
done

say "Scratch project and DESK node service"
mkdir -p "${VAL_PROJECTS}/${VAL_PROJECT}"
tokfile="$(secret_file service_token "python3 -c 'import secrets; print(secrets.token_urlsafe(32))'")"
pidfile="${VAL_DIR}/service.pid"
if [[ -s "$pidfile" ]] && kill -0 "$(cat "$pidfile")" 2>/dev/null; then
  info "the node service is already running (pid $(cat "$pidfile"))"
else
  (cd "${DESK_REPO}" && DESK_WEFT_TOKEN="$(cat "$tokfile")" nohup python3 tools/desk.py weft serve --port "${SERVICE_PORT}" \
     --projects-root "${VAL_PROJECTS}" >"${VAL_LOGS}/service.log" 2>&1 & echo $! > "$pidfile")
fi
for _ in $(seq 1 40); do curl -fsS "${SERVICE_URL}/health" >/dev/null 2>&1 && break; sleep 0.5; done
curl -fsS "${SERVICE_URL}/health" >/dev/null && record service.up PASS "${SERVICE_URL}" || { record service.up FAIL "see ${VAL_LOGS}/service.log"; exit 1; }
code="$(curl -s -o /dev/null -w '%{http_code}' -X POST "${SERVICE_URL}/v1/nodes/DeskRequirementIntake" -d '{}')"
[[ "$code" == "401" ]] && record service.needs_token PASS "a call without the token gets 401" || { record service.needs_token FAIL "got HTTP ${code}"; exit 1; }

say "Give Weft the node-service token, and pick it for every DESK call"
conn_id="${DESK_WEFT_CONNECTION_ID:-}"
for wf in requirement_to_profile hardware_design; do
  staged="$(staged_dir "$wf")"
  mapfile -t addrs < <(desk weft addresses "$wf")
  (( ${#addrs[@]} > 0 )) || { record "connect.$wf" FAIL "no HttpRequest addresses listed"; exit 1; }
  if [[ -z "$conn_id" ]]; then
    # One stored connection for the whole install, created through the first node. The value comes from an
    # environment variable (--set-env), so the token never rides a command line.
    (cd "$staged" && DESK_WEFT_BEARER="Bearer $(cat "$tokfile")" weft connect "${addrs[0]}" --door own \
       --set header=Authorization --set-env value=DESK_WEFT_BEARER --label "${CONNECTION_LABEL}") >"${VAL_LOGS}/connect.create.log" 2>&1 \
      || { record connect.create FAIL "see ${VAL_LOGS}/connect.create.log"; exit 1; }
    conn_id="$(cd "$staged" && weft --json connect "${addrs[0]}" --list | python3 -c 'import json,sys; print(json.loads(sys.stdin.readline())["picked"] or "")')"
    [[ -n "$conn_id" ]] || { record connect.create FAIL "the connection was stored but is not picked for ${addrs[0]}"; exit 1; }
    printf '%s' "$conn_id" > "${VAL_DIR}/connection.id"
    record connect.create PASS "stored connection ${conn_id} (${CONNECTION_LABEL})"
  fi
  picked=0
  for a in "${addrs[@]}"; do
    got="$(cd "$staged" && weft --json connect "$a" --grant "$conn_id" | python3 -c 'import json,sys; print(json.loads(sys.stdin.readline())["picked"])')"
    [[ "$got" == "$conn_id" ]] || { record "connect.$wf" FAIL "$a: picked ${got:-nothing}"; exit 1; }
    picked=$((picked + 1))
  done
  record "connect.$wf" PASS "${picked} DESK node call(s) carry the node-service key"
done

say "DESK is ready. Next: 40_run_requirement_to_profile.sh"
