"""Export Gerber+drill zip of the ACTIVE PCB document (must be the recovery copy) into the release folder.
Usage: python output/sensor_patch_6up_release/tools_export_gerber.py <expected_doc_uuid> <out_subdir>
Full-object export: all object classes, both plated and non-plated drill info, drill table, mm units."""
import sys, os, json, hashlib, zipfile
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, os.path.join(ROOT, "tools"))
from _common import ex  # noqa
from desk.bridge import fetch_file, guard  # noqa

doc, sub = sys.argv[1], sys.argv[2]
dest = os.path.join(HERE, sub)
js = guard(doc, open_doc=False) + '''
const f=await eda.pcb_ManufactureData.getGerberFile("sensor_patch_6up_gerber", false, "mm", {integerNumber:4, decimalNumber:5},
  {metallicDrillingInformation:true, nonMetallicDrillingInformation:true, drillTable:true, flyingProbeTestingFile:false},
  undefined,
  ["Pad","Via","Track","Text","Image","Dimension","BoardOutline","BoardCutout","CopperFilled","SolidRegion","FPCStiffener","Line","PlaneZone","ComponentProperty","ComponentSilkscreen","TearDrop"]);'''
p = fetch_file(js, dest, prefix="", timeout=600)
h = hashlib.sha256(open(p, "rb").read()).hexdigest()
names = zipfile.ZipFile(p).namelist() if zipfile.is_zipfile(p) else []
print(json.dumps({"file": p, "bytes": os.path.getsize(p), "sha256": h, "entries": names}, indent=1))
