"""
Add Drill-Through Functionality to Power BI Report
This updates the report to enable drill-through on analysis pages
"""

import json
from pathlib import Path

def add_drill_through():
    """Add drill-through configuration to analysis pages"""
    
    base_dir = Path(__file__).parent
    report_path = base_dir / "HorseShows.Report" / "report.json"
    
    print("=" * 60)
    print("Adding Drill-Through Functionality")
    print("=" * 60)
    print()
    
    # Read existing report
    with open(report_path, 'r') as f:
        report = json.load(f)
    
    # Add drill-through to Rider Analysis (page index 1)
    if len(report['sections']) > 1:
        rider_page = report['sections'][1]
        rider_page['filters'] = json.dumps([
            {
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
        ])
        
        # Mark as drill-through target
        config = json.loads(rider_page.get('config', '{}'))
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
        rider_page['config'] = json.dumps(config)
        print("[OK] Added drill-through to Rider Analysis page")
    
    # Add drill-through to Horse Analysis (page index 2)
    if len(report['sections']) > 2:
        horse_page = report['sections'][2]
        horse_page['filters'] = json.dumps([
            {
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
        ])
        
        config = json.loads(horse_page.get('config', '{}'))
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
        horse_page['config'] = json.dumps(config)
        print("[OK] Added drill-through to Horse Analysis page")
    
    # Add drill-through to Trainer Analysis (page index 3)
    if len(report['sections']) > 3:
        trainer_page = report['sections'][3]
        trainer_page['filters'] = json.dumps([
            {
                "name": "Trainer Drill-Through",
                "expression": {
                    "Column": {
                        "Expression": {
                            "SourceRef": {
                                "Source": "dimTrainers"
                            }
                        },
                        "Property": "TrainerName"
                    }
                },
                "type": "Advanced",
                "howCreated": "User"
            }
        ])
        
        config = json.loads(trainer_page.get('config', '{}'))
        config['drillThroughFields'] = [
            {
                "Column": {
                    "Expression": {
                        "SourceRef": {
                            "Source": "dimTrainers"
                        }
                    },
                    "Property": "TrainerName"
                }
            }
        ]
        trainer_page['config'] = json.dumps(config)
        print("[OK] Added drill-through to Trainer Analysis page")
    
    # Save updated report
    with open(report_path, 'w') as f:
        json.dump(report, f, indent=2)
    
    print()
    print("=" * 60)
    print("[SUCCESS] Drill-through functionality added!")
    print("=" * 60)
    print()
    print("How to use drill-through:")
    print("1. Right-click on any rider name in a table or chart")
    print("2. Select 'Drill through' > 'Rider Analysis'")
    print("3. The Rider Analysis page opens, filtered to that rider")
    print()
    print("Same works for:")
    print("- Horse names -> Horse Analysis page")
    print("- Trainer names -> Trainer Analysis page")
    print()
    print("A back button will appear to return to the previous page")
    print()

if __name__ == "__main__":
    add_drill_through()
