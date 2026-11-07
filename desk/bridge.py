"""DESK bridge: run JavaScript inside the live EasyEDA Pro client through the EasyEDA API Gateway.
Every DESK tool talks to EasyEDA only through ex(). Nothing else opens sockets."""
import json, os, sys, time, urllib.request, io

if hasattr(sys.stdout, "buffer"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

def _discover():
    """EDA_PORT env wins; else scan 49620-49629 for the bridge /health handshake (service: easyeda-bridge)."""
    if os.environ.get("EDA_PORT"):
        return int(os.environ["EDA_PORT"])
    for port in range(49620, 49630):
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{port}/health", timeout=1) as r:
                if b"easyeda-bridge" in r.read():
                    return port
        except OSError:
            pass
    return 49620


PORT = _discover()


def _find_target_window(uuids=("c75145b22afda01f", "d8c5340d62893518")):
    try:
        req = urllib.request.Request(f"http://127.0.0.1:{PORT}/eda-windows")
        with urllib.request.urlopen(req, timeout=1) as r:
            wins = json.loads(r.read().decode("utf-8")).get("windows", [])
        for w in wins:
            wid = w.get("windowId")
            if not wid: continue
            try:
                chk = urllib.request.Request(f"http://127.0.0.1:{PORT}/execute",
                    data=json.dumps({"code": "const d=await eda.dmt_SelectControl.getCurrentDocumentInfo(); return d?d.uuid:null;", "windowId": wid}).encode("utf-8"),
                    headers={"Content-Type": "application/json"})
                with urllib.request.urlopen(chk, timeout=2) as cr:
                    cres = json.loads(cr.read().decode("utf-8"))
                    if cres.get("result") in uuids:
                        return wid
            except Exception:
                pass
    except Exception:
        pass
    return None


def ex(code, timeout=280, retries=1, window_id=None):
    """Execute JS (body of an async function; use `return` for the result). Raises SystemExit on EDA error."""
    target_window = window_id or os.environ.get("EDA_WINDOW_ID")
    if not target_window:
        try:
            p_path = os.path.join("projects", "WATCH", "project.json")
            if os.path.exists(p_path):
                target_window = json.load(open(p_path, encoding="utf-8")).get("window_id")
        except Exception:
            pass
    for attempt in range(retries + 1):
        payload = {"code": code}
        if target_window:
            payload["windowId"] = target_window
        body = json.dumps(payload).encode("utf-8")
        try:
            req = urllib.request.Request(f"http://127.0.0.1:{PORT}/execute", data=body,
                                         headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                resp = json.loads(r.read().decode("utf-8"))
            if not resp.get("success"):
                raise SystemExit("EDA error: " + str(resp.get("error")))
            return resp.get("result")
        except (OSError, TimeoutError) as e:
            # If target window disconnected or changed, auto-resolve target window
            resolved = _find_target_window()
            if resolved and resolved != target_window:
                target_window = resolved
                try:
                    p_path = os.path.join("projects", "WATCH", "project.json")
                    if os.path.exists(p_path):
                        pj = json.load(open(p_path, encoding="utf-8"))
                        pj["window_id"] = resolved
                        json.dump(pj, open(p_path, "w", encoding="utf-8"), indent=1)
                except Exception:
                    pass
                continue
            if attempt == retries:
                raise SystemExit(f"Bridge not reachable on port {PORT}: {e}\n"
                                 "-> Is EasyEDA Pro open with the API Gateway connected? (see docs/06_EASYEDA_API.md)")
            time.sleep(2)


def guard(doc_uuid, open_doc=True):
    """JS prefix that (optionally) opens the document and refuses to run on any other sheet."""
    o = f'await eda.dmt_EditorControl.openDocument("{doc_uuid}"); await new Promise(r=>setTimeout(r,1200));' if open_doc else ""
    return (o + f'const __D=await eda.dmt_SelectControl.getCurrentDocumentInfo();'
                f'if(!__D||__D.uuid!=="{doc_uuid}") return {{error:"WRONG SHEET", active:__D&&__D.uuid}};\n')


def load_project(path):
    p = os.path.join(path, "project.json")
    if not os.path.exists(p):
        raise SystemExit(f"No project.json in {path}. Copy templates/project/ first.")
    return json.load(open(p, encoding="utf-8"))


def check(res):
    if isinstance(res, dict) and res.get("error"):
        raise SystemExit(f"STOP: {res}")
    return res


_B64 = ('if(!f) return {error:"NO FILE returned by EasyEDA"}; const ab=await f.arrayBuffer(); let s=""; const u=new Uint8Array(ab);'
        'for(let i=0;i<u.length;i+=0x8000){s+=String.fromCharCode.apply(null,u.subarray(i,i+0x8000));} return {name:f.name,b64:btoa(s)};')


def fetch_file(js_get, dest_dir, prefix="", timeout=280, window_id=None):
    """js_get must assign `const f = await <EasyEDA call returning File>;`. Saves the file, returns its path."""
    import base64
    r = check(ex(js_get + _B64, timeout=timeout, window_id=window_id))
    os.makedirs(dest_dir, exist_ok=True)
    path = os.path.join(dest_dir, prefix + r["name"])
    with open(path, "wb") as f:
        f.write(base64.b64decode(r["b64"]))
    return path
