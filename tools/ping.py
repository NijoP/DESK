"""Step 0 smoke test. Prints the open project and the ACTIVE document (copy its uuid into project.json).
Usage: python tools/ping.py"""
from _common import ex
import json
print(json.dumps(ex('''
const p=await eda.dmt_Project.getCurrentProjectInfo();
const d=await eda.dmt_SelectControl.getCurrentDocumentInfo();
return {project:p&&{name:p.friendlyName||p.name,uuid:p.uuid}, active_document:d};'''), indent=2, ensure_ascii=False))
