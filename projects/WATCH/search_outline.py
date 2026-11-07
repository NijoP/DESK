import urllib.request

data = urllib.request.urlopen('https://modules.lceda.cn/pro-pcb/3.2.149.5378b690/js/pcb.js').read().decode('utf-8', errors='ignore')
kw = '"Board Outline"'
pos = 0
found = []
while True:
    pos = data.find(kw, pos)
    if pos == -1: break
    found.append((pos, data[max(0, pos-100):min(len(data), pos+150)]))
    pos += len(kw)

print(f"Total occurrences: {len(found)}")
for p, snippet in found[:10]:
    print(f"--- at {p} ---")
    print(snippet)
