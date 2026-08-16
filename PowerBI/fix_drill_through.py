"""
Fix drill-through - add it properly to Rider and Horse Analysis pages
"""
import json
from pathlib import Path

def fix_drill_through():
    """Fix drill-through configuration"""
    
    base_dir = Path(__file__).parent
    report_path = base_dir / "HorseShows.Report" / "report.json"
    
    print("\n" + "=" * 60)
    print("FIXING DRILL-THROUGH")
    print("=" * 60 + "\n")
    
    # Read existing report
    with open(report_path, 'r', encoding='utf-8') as f:
        report = json.load(f)
    
    # Find pages by name
    for section in report['sections']:
        page_name = section.get('displayName', 'Unknown')
        
        if page_name == 'Rider Analysis':
            print(f"Fixing {page_name}...")
            
            # Parse existing config (it's a string)
            config_str = section.get('config', '{}')
            if isinstance(config_str, str):
                config = json.loads(config_str) if config_str else {}
            else:
                config = config_str
            
            # Add drill-through fields
            config['drillThroughFields'] = [
                {
                    "Column": {
                        "Expression": {
                            "SourceRef": {
                                "Source": "dimRiders"
                            }
                        },
                        "Property": "RiderName"
                    }
                }
            ]
            
            # Save back as string
            section['config'] = json.dumps(config)
            print(f"  [OK] Added drillThroughFields to config")
        
        elif page_name == 'Horse Analysis':
            print(f"Fixing {page_name}...")
            
            # Parse existing config (it's a string)
            config_str = section.get('config', '{}')
            if isinstance(config_str, str):
                config = json.loads(config_str) if config_str else {}
            else:
                config = config_str
            
            # Add drill-through fields
            config['drillThroughFields'] = [
                {
                    "Column": {
                        "Expression": {
                            "SourceRef": {
                                "Source": "dimHorses"
                            }
                        },
                        "Property": "HorseName"
                    }
                }
            ]
            
            # Save back as string
            section['config'] = json.dumps(config)
            print(f"  [OK] Added drillThroughFields to config")
    
    # Save updated report
    with open(report_path, 'w', encoding='utf-8') as f:
        json.dump(report, f, indent=2)
    
    print("\n" + "=" * 60)
    print("[SUCCESS] Drill-through fixed!")
    print("=" * 60 + "\n")

if __name__ == "__main__":
    fix_drill_through()
