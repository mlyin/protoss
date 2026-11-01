#!/usr/bin/env python3
"""Export the native vector mascot states from the editable brand SVG."""
from pathlib import Path
import xml.etree.ElementTree as ET

root = Path(__file__).resolve().parents[1]
source = (root / "brand/probe.svg").read_text()
directory = root / "web/public/probe"
directory.mkdir(exist_ok=True)
for state in ("idle", "thinking", "talking", "working", "success"):
    svg = source.replace('class="probe idle"', f'class="probe {state}"')
    svg = svg.replace("Protoss Probe, hovering", f"Protoss Probe, {state}")
    (directory / f"{state}.svg").write_text(svg)
import re
copies = []
for index in range(2):
    svg = source.replace('class="probe idle"', 'class="probe talking"')
    svg = re.sub(r'id="([^"]+)"', lambda m: f'id="p{index}-{m[1]}"', svg)
    svg = re.sub(r'url\(#([^)]+)\)', lambda m: f'url(#p{index}-{m[1]})', svg)
    svg = svg.replace('aria-labelledby="title"', f'aria-labelledby="p{index}-title"')
    svg = svg.replace('viewBox="0 0 320 320"', 'x="0" y="0" width="320" height="320" viewBox="0 0 320 320"')
    copies.append('<g transform="translate(640 0) scale(-1 1)">' + svg + '</g>' if index else svg)
(directory / 'conversation.svg').write_text('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 640 320" role="img" aria-label="Two Protoss Probes talking">' + ''.join(copies) + '</svg>')
print("Exported six standalone vector SVGs to web/public/probe/")

# A still, tightly framed icon for favicons and legacy mark URLs.
ET.register_namespace('', 'http://www.w3.org/2000/svg')
icon = ET.fromstring(source)
icon.set('viewBox', '25 20 270 270')
icon.set('class', 'probe-icon')
for child in list(icon):
    if child.tag.endswith('style') or child.attrib.get('class', '').endswith('-effects'):
        icon.remove(child)
for element in icon.iter():
    if element.attrib.get('class') == 'outline':
        element.attrib.update({'stroke': '#453221', 'stroke-width': '4', 'stroke-linejoin': 'round', 'stroke-linecap': 'round'})
    if element.tag.endswith('title'):
        element.text = 'Protoss Probe'
icon_svg = ET.tostring(icon, encoding='unicode')
for target in ['web/public/favicon.svg', 'web/public/mark.svg', 'brand/mark-light.svg', 'brand/mark-dark.svg']:
    (root / target).write_text(icon_svg)
