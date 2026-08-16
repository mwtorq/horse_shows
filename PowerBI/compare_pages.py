"""
Compare Trainer Analysis (working) vs Rider Analysis (not working)
"""
import json

report_path = r"HorseShows.Report\report.json"

with open(report_path, 'r', encoding='utf-8') as f:
    report = json.load(f)

print("\n" + "="*60)
print("COMPARISON: TRAINER vs RIDER")
print("="*60 + "\n")

for page_name in ['Trainer Analysis', 'Rider Analysis']:
    print(f"\n{'='*60}")
    print(f"{page_name.upper()}")
    print('='*60)
    
    for section in report.get('sections', []):
        if section.get('displayName', '') == page_name:
            
            # Config
            config_raw = section.get('config', '')
            if isinstance(config_raw, str):
                config = json.loads(config_raw) if config_raw else {}
            else:
                config = config_raw
            
            print("\nCONFIG drillThroughFields:")
            if 'drillThroughFields' in config:
                print(json.dumps(config['drillThroughFields'], indent=2))
            else:
                print("  MISSING!")
            
            # Filters
            filters_raw = section.get('filters', [])
            if isinstance(filters_raw, str):
                filters = json.loads(filters_raw) if filters_raw else []
            else:
                filters = filters_raw
            
            print(f"\nFILTERS ({len(filters)} total):")
            
            # Look for drill-through related filters
            drill_filters = [f for f in filters if isinstance(f, dict) and 
                           'Drill' in str(f) or 'drillthrough' in str(f).lower()]
            
            if drill_filters:
                print("Drill-through filters found:")
                for f in drill_filters:
                    print(json.dumps(f, indent=2))
            else:
                print("  No drill-through specific filters")
                if len(filters) > 0:
                    print(f"\n  First filter as example:")
                    print(json.dumps(filters[0] if filters else {}, indent=2)[:500])

print("\n" + "="*60)
print("END COMPARISON")
print("="*60 + "\n")
