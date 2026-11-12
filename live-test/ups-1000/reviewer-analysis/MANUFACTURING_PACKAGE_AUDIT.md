# Manufacturing package audit (manufacturing-revA/ plus records)
| Deliverable | Status |
|---|---|
| .epro project export | ABSENT |
| Schematic PDF | ABSENT |
| Gerber ZIP | ABSENT |
| Drill files | ABSENT |
| BOM | PRESENT (projects/UPS_1000/bom.csv, BOM_SELECTION.md); 10 items TO VERIFY |
| CPL / pick-and-place | ABSENT |
| Stackup notes | PARTIAL (FAB_AND_ASSEMBLY_NOTES.md; dielectric thicknesses TBD) |
| DRC report | PARTIAL (unrouted board, 349 violations; not a pass) |
| ERC report | PRESENT (0 errors) |
| Electrical report | PARTIAL (conductor_sizing.txt, block qa calcs) |
| Thermal report | PARTIAL (hand calc, UNSUPPORTED rule, no measurement) |
| Preflight report | PRESENT (preflight.json passed, pre-routing) |
| SHA-256 manifest | PRESENT, 71 files, 68 match; 3 live logs changed after generation. Self-labelled "NOT A FABRICATION RELEASE" (honest) |
| Mounting holes | ABSENT (disclosed release blocker) |

Overall: no fabrication-ready deliverable exists. Honesty of the package is high.
