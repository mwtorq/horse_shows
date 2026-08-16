"""
Debug Rider Analysis drill-through configuration
"""
import json

report_path = r"HorseShows.Report\report.json"

with open(report_path, 'r', encoding='utf-8') as f:
    report = json.load(f)

print("\n" + "="*60)
print("RIDER ANALYSIS PAGE DEBUG")
print("="*60 + "\n")

for idx, section in enumerate(report.get('sections', [])):
    page_name = section.get('displayName', 'Unknown')
    
    if page_name == 'Rider Analysis':
        print(f"Page Index: {idx}")
        print(f"Page Name: {page_name}")
        print("\n" + "-"*40)
        print("CONFIG (raw):")
        print("-"*40)
        config_raw = section.get('config', '')
        print(f"Type: {type(config_raw)}")
        print(f"Length: {len(config_raw) if isinstance(config_raw, str) else 'N/A'}")
        
        if isinstance(config_raw, str):
            try:
                config = json.loads(config_raw)
                print(f"\nParsed config keys: {list(config.keys())}")
                print(f"\nFull parsed config:")
                print(json.dumps(config, indent=2))
            except Exception as e:
                print(f"\nERROR parsing config: {e}")
                print(f"Raw config (first 500 chars): {config_raw[:500]}")
        
        print("\n" + "-"*40)
        print("FILTERS:")
        print("-"*40)
        filters = section.get('filters', [])
        print(f"Type: {type(filters)}")
        if isinstance(filters, str):
            print(f"Filters is a string, length: {len(filters)}")
            try:
                filters_parsed = json.loads(filters)
                print(f"Parsed filters count: {len(filters_parsed)}")
                print(json.dumps(filters_parsed, indent=2))
            except Exception as e:
                print(f"ERROR parsing filters: {e}")
        else:
            print(f"Filters count: {len(filters)}")
            print(json.dumps(filters, indent=2))
        
        print("\n" + "-"*40)
        print("OTHER PROPERTIES:")
        print("-"*40)
        for key in section.keys():
            if key not in ['config', 'filters', 'displayName', 'visualContainers']:
                print(f"{key}: {section[key]}")

print("\n" + "="*60)
print("END DEBUG")
print("="*60 + "\n")
