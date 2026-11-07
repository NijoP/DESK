import json

dump = json.load(open('projects/WATCH/state/pcb_dump.json'))
MIL = 39.37007874
sample = ['C1', 'C6', 'R1', 'R8', 'LED1', 'SW1', 'U1', 'J1', 'J2', 'J6', 'J5', 'U2', 'U3', 'U4', 'U8', 'MIC1', 'U5']
for ref in sample:
    c = dump[ref]
    b = c['bbox']
    w = (b[1] - b[0]) / MIL
    h = (b[3] - b[2]) / MIL
    print(f"{ref:5s} ({c.get('fp', ''):25s}): size {w:5.2f} x {h:5.2f} mm | bbox mm: [{b[0]/MIL:5.2f}, {b[1]/MIL:5.2f}, {b[2]/MIL:5.2f}, {b[3]/MIL:5.2f}]")
