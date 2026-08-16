"""
Examine the Trainer Analysis page in extreme detail to understand
why it works (assuming it actually works)
"""
import json

report_path = r"HorseShows.Report\report.json"

with open(report_path, 'r', encoding='utf-8') as f:
    report = json.load(f)

print("\n" + "="*70)
print("TRAINER ANALYSIS - COMPLETE STRUCTURE")
print("="*70 + "\n")

for section in report.get('sections', []):
    if section.get('displayName', '') == 'Trainer Analysis':
        
        # Print ALL keys
        print("ALL SECTION KEYS:")
        print("-" * 70)
        for key in sorted(section.keys()):
            if key not in ['visualContainers', 'config', 'filters']:
                print(f"  {key}: {section[key]}")
        
        print("\n" + "="*70)
        print("CONFIG STRUCTURE")
        print("="*70)
        config_raw = section.get('config', '')
        if isinstance(config_raw, str):
            config = json.loads(config_raw) if config_raw else {}
            print(json.dumps(config, indent=2))
        
        print("\n" + "="*70)
        print("FILTERS STRUCTURE (all filters)")
        print("="*70)
        filters_raw = section.get('filters', [])
        if isinstance(filters_raw, str):
            filters = json.loads(filters_raw) if filters_raw else []
        else:
            filters = filters_raw
        
        print(f"Total filters: {len(filters)}\n")
        
        for idx, f in enumerate(filters):
            if isinstance(f, dict):
                # Look for key properties
                filter_type = f.get('type', 'unknown')
                filter_name = f.get('name', 'unnamed')
                how_created = f.get('howCreated', 'unknown')
                
                print(f"Filter {idx}: {filter_name}")
                print(f"  Type: {filter_type}, HowCreated: {how_created}")
                
                # Show full structure for drill-through filters
                if 'Drill' in filter_name:
                    print(f"  FULL STRUCTURE:")
                    print(json.dumps(f, indent=4))
                print()

print("="*70 + "\n")
