"""Create projects/<NAME>/ from templates/project. Usage: python tools/new_project.py MY_PRODUCT"""
import sys, os, shutil, json
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
name = sys.argv[1]
dst = os.path.join(ROOT, "projects", name)
if os.path.exists(dst): raise SystemExit(f"{dst} exists")
shutil.copytree(os.path.join(ROOT, "templates", "project"), dst)
for f in ("REQUIREMENTS.md", "BLOCK_PLAN.md", "RESULT.md"):
    shutil.copy(os.path.join(ROOT, "templates", f), os.path.join(dst, f))
pj = os.path.join(dst, "project.json"); p = json.load(open(pj)); p["name"] = name; json.dump(p, open(pj, "w"), indent=1)
print("created", dst, "-> fill REQUIREMENTS.md, then BLOCK_PLAN.md (docs/03_BLOCK_WORKFLOW.md)")
