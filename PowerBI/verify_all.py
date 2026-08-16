"""
Check all three analysis pages
"""
import json

report_path = r"HorseShows.Report\report.json"

with open(report_path, 'r', encoding='utf-8') as f:
    report = json.load(f)

print("\n" + "="*60)
print("ALL ANALYSIS PAGES - DRILL-THROUGH STATUS")
print("="*60 + "\n")

for page_name in ['Rider Analysis', 'Horse Analysis', 'Trainer Analysis']:
    for section in report.get('sections', []):
        if section.get('displayName', '') == page_name:
            
            # Config
            config_raw = section.get('config', '')
            if isinstance(config_raw, str):
                config = json.loads(config_raw) if config_raw else {}
            else:
                config = config_raw
            
            has_config = 'drillThroughFields' in config
            
            # Filters
            filters_raw = section.get('filters', [])
            if isinstance(filters_raw, str):
                filters = json.loads(filters_raw) if filters_raw else []
            else:
                filters = filters_raw
            
            has_filter = any('Drill-Through' in f.get('name', '') for f in filters if isinstance(f, dict))
            
            status = "[OK]" if (has_config and has_filter) else "[ERROR]"
            print(f"{status} {page_name}")
            print(f"    Config: {'YES' if has_config else 'NO'}")
            print(f"    Filter: {'YES' if has_filter else 'NO'}")
            
            if has_filter:
                drill_filter = next(f for f in filters if isinstance(f, dict) and 'Drill-Through' in f.get('name', ''))
                source = drill_filter['expression']['Column']['Expression']['SourceRef']['Source']
                prop = drill_filter['expression']['Column']['Property']
                print(f"    Field: {source}[{prop}]")
            print()

print("="*60 + "\n")
