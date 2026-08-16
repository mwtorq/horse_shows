"""
Check drill-through configuration in report.json
"""
import json

report_path = r"HorseShows.Report\report.json"

with open(report_path, 'r', encoding='utf-8') as f:
    report = json.load(f)

print("\n" + "="*60)
print("DRILL-THROUGH CONFIGURATION CHECK")
print("="*60 + "\n")

analysis_pages = ['Rider Analysis', 'Horse Analysis', 'Trainer Analysis']

for section in report.get('sections', []):
    page_name = section.get('displayName', 'Unknown')
    
    if page_name not in analysis_pages:
        continue
    
    print(f"\n[PAGE] {page_name}")
    print("-" * 40)
    
    # Check filters
    filters = section.get('filters', [])
    print(f"Filters: {len(filters)} found")
    for f in filters:
        if isinstance(f, dict):
            print(f"  - {json.dumps(f, indent=4)}")
    
    # Check config
    config = section.get('config', {})
    if isinstance(config, str):
        try:
            config = json.loads(config)
        except:
            print(f"  [WARNING] Config is a string, not parsed: {config[:100]}...")
            continue
    
    # Look for drill-through fields
    if 'drillThroughFields' in config:
        print(f"[OK] drillThroughFields found:")
        fields = config['drillThroughFields']
        print(f"  {json.dumps(fields, indent=4)}")
    else:
        print(f"[ERROR] No drillThroughFields in config")
        print(f"Config keys: {list(config.keys())}")

print("\n" + "="*60)
print("END OF CHECK")
print("="*60 + "\n")
