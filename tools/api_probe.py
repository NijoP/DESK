"""Discover the EasyEDA Pro API that ACTUALLY exists in the running client (read-only).
Usage: python tools/api_probe.py            -> library/api_map.json  {module: [methods]}, plus EasyEDA version
Compare with the documented API (docs/06_EASYEDA_API.md) and with library/api_verified.json (calls proven by tests).
A documented method is only trusted once a test that uses it has passed (tools/live_test.py records that)."""
import json, os, sys
from _common import ex, S

r = ex(r'''
const out={}; const ver={};
try{ver.editor=await eda.sys_Environment.getEditorCurrentVersion();}catch(e){}
try{ver.client=eda.sys_Environment.isClient?await eda.sys_Environment.isClient():null;}catch(e){}
for(const k of Object.keys(eda).sort()){const o=eda[k]; if(!o||typeof o!=="object")continue;
 const names=new Set(); let p=o; let guard=0;
 while(p&&p!==Object.prototype&&guard++<5){for(const n of Object.getOwnPropertyNames(p)){if(n!=="constructor"&&typeof o[n]==="function")names.add(n);} p=Object.getPrototypeOf(p);}
 out[k]=[...names].sort();}
return {ver,out};''', timeout=60)
path = os.path.join(S.ROOT, "library", "api_map.json")
with open(path, "w", encoding="utf-8") as f:
    json.dump({"version": r["ver"], "modules": r["out"]}, f, indent=1)
n = sum(len(v) for v in r["out"].values())
print(f"EasyEDA {r['ver']}: {len(r['out'])} modules, {n} methods -> library/api_map.json")
