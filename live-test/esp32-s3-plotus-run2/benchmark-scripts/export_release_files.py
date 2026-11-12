"""Post-remediation export of manufacturing + design files from the live EasyEDA project (read-only exports; no orders)."""
import sys, os, shutil
sys.path.insert(0, r"C:\nemotron test\Plotus\DESK")
from desk.bridge import fetch_file, guard
W = "17ea844c-a5d0-4a6a-b78a-b64521ae7895"
GP, GS = guard("bb03148ad5ac7687"), guard("a5b5ba31d2ccd917")
out = os.path.join(os.path.dirname(__file__), "..", "manufacturing", "revA_run2b"); os.makedirs(out, exist_ok=True)
N = "PLOTUS_ESP32S3_revA"
jobs = {"gerber": GP + f'const f=await eda.pcb_ManufactureData.getGerberFile("{N}_gerber");',
        "bom": GP + f'const f=await eda.pcb_ManufactureData.getBomFile("{N}_bom","csv");',
        "cpl": GP + f'const f=await eda.pcb_ManufactureData.getPickAndPlaceFile("{N}_cpl","csv");',
        "schematic_pdf": GS + f'const f=await eda.sch_ManufactureData.getExportDocumentFile("{N}_schematic","PDF");',
        "schematic_svg": GS + f'const f=await eda.sch_ManufactureData.getSvgFile("{N}_schematic");',
        "project_epro": f'const f=await eda.sys_FileManager.getProjectFileByProjectUuid("4b42a95a5f744392ac42db2ff05eea5c","{N}_project","","epro");'}
for k in (sys.argv[1:] or jobs):
    try:
        p = fetch_file(jobs[k], out, window_id=W, timeout=280); print("OK", k, os.path.basename(p), os.path.getsize(p))
    except BaseException as e:
        print("FAIL", k, str(e)[:200])
