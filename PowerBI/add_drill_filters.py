"""
Add drill-through FILTERS to pages (not just config)
"""
import json
from pathlib import Path

def add_drill_filters():
    """Add drill-through filters to analysis pages"""
    
    base_dir = Path(__file__).parent
    report_path = base_dir / "HorseShows.Report" / "report.json"
    
    print("\n" + "=" * 60)
    print("ADDING DRILL-THROUGH FILTERS")
    print("=" * 60 + "\n")
    
    # Read existing report
    with open(report_path, 'r', encoding='utf-8') as f:
        report = json.load(f)
    
    # Find pages by name and add filters
    for section in report['sections']:
        page_name = section.get('displayName', 'Unknown')
        
        if page_name == 'Rider Analysis':
            print(f"Adding filter to {page_name}...")
            
            # Parse existing filters
            filters_str = section.get('filters', '[]')
            if isinstance(filters_str, str):
                filters = json.loads(filters_str) if filters_str else []
            else:
                filters = filters_str if isinstance(filters_str, list) else []
            
            # Add drill-through filter
            drill_filter = {
                "name": "Rider Drill-Through",
                "expression": {
                    "Column": {
                        "Expression": {
                            "SourceRef": {
                                "Source": "dimRiders"
                            }
                        },
                        "Property": "RiderName"
                    }
                },
                "type": "Advanced",
                "howCreated": "User"
            }
            
            # Check if already exists
            has_drill_filter = any(f.get('name') == 'Rider Drill-Through' for f in filters if isinstance(f, dict))
            
            if not has_drill_filter:
                filters.append(drill_filter)
                section['filters'] = json.dumps(filters)
                print(f"  [OK] Added Rider drill-through filter")
            else:
                print(f"  [SKIP] Filter already exists")
        
        elif page_name == 'Horse Analysis':
            print(f"Adding filter to {page_name}...")
            
            # Parse existing filters
            filters_str = section.get('filters', '[]')
            if isinstance(filters_str, str):
                filters = json.loads(filters_str) if filters_str else []
            else:
                filters = filters_str if isinstance(filters_str, list) else []
            
            # Add drill-through filter
            drill_filter = {
                "name": "Horse Drill-Through",
                "expression": {
                    "Column": {
                        "Expression": {
                            "SourceRef": {
                                "Source": "dimHorses"
                            }
                        },
                        "Property": "HorseName"
                    }
                },
                "type": "Advanced",
                "howCreated": "User"
            }
            
            # Check if already exists
            has_drill_filter = any(f.get('name') == 'Horse Drill-Through' for f in filters if isinstance(f, dict))
            
            if not has_drill_filter:
                filters.append(drill_filter)
                section['filters'] = json.dumps(filters)
                print(f"  [OK] Added Horse drill-through filter")
            else:
                print(f"  [SKIP] Filter already exists")
    
    # Save updated report
    with open(report_path, 'w', encoding='utf-8') as f:
        json.dump(report, f, indent=2)
    
    print("\n" + "=" * 60)
    print("[SUCCESS] Drill-through filters added!")
    print("=" * 60 + "\n")

if __name__ == "__main__":
    add_drill_filters()
