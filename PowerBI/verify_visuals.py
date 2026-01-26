import json

with open('HorseShows.Report/report.json', 'r') as f:
    report = json.load(f)

print("=" * 60)
print("Visual Verification Report")
print("=" * 60)
print()

total_visuals = 0
for section in report['sections']:
    visual_count = len(section['visualContainers'])
    total_visuals += visual_count
    print(f"{section['displayName']}: {visual_count} visuals")

print()
print(f"Total visuals across all pages: {total_visuals}")
print()

if total_visuals > 0:
    print("[SUCCESS] Visuals have been created!")
    print()
    print("Sample visual from Page 1:")
    if report['sections'][0]['visualContainers']:
        first_visual = report['sections'][0]['visualContainers'][0]
        print(f"  Position: x={first_visual['x']}, y={first_visual['y']}")
        print(f"  Size: {first_visual['width']}x{first_visual['height']}")
        config = json.loads(first_visual['config'])
        visual_type = config['singleVisual']['visualType']
        print(f"  Type: {visual_type}")
else:
    print("[ERROR] No visuals found!")
