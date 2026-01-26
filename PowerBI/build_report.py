"""
Power BI Report Builder for HorseShows Database
This script creates a Power BI report structure programmatically
"""

import json
import os
from pathlib import Path
import uuid

def create_guid():
    """Generate a new GUID"""
    return str(uuid.uuid4())

def create_directory_structure():
    """Create the .pbip project directory structure"""
    base_dir = Path(__file__).parent
    
    # Create directories
    report_dir = base_dir / "HorseShows.Report"
    model_dir = base_dir / "HorseShows.SemanticModel"
    
    report_dir.mkdir(exist_ok=True)
    model_dir.mkdir(exist_ok=True)
    
    # Note: .platform is a file, not a directory
    
    return base_dir, report_dir, model_dir

def create_pbip_file(base_dir):
    """Create the main .pbip file"""
    pbip_content = {
        "version": "1.0",
        "artifacts": [
            {
                "report": {
                    "path": "HorseShows.Report",
                    "type": "Report"
                }
            },
            {
                "dataset": {
                    "path": "HorseShows.SemanticModel",
                    "type": "SemanticModel"
                }
            }
        ]
    }
    
    pbip_path = base_dir / "HorseShows.pbip"
    with open(pbip_path, 'w') as f:
        json.dump(pbip_content, f, indent=2)
    print(f"[OK] Created {pbip_path}")

def create_report_definition(report_dir):
    """Create report definition.pbir"""
    definition = {
        "version": "1.0",
        "datasetReference": {
            "byPath": {
                "path": "../HorseShows.SemanticModel"
            }
        }
    }
    
    def_path = report_dir / "definition.pbir"
    with open(def_path, 'w') as f:
        json.dump(definition, f, indent=2)
    print(f"[OK] Created {def_path}")

def create_minimal_report_json(report_dir):
    """Create a minimal report.json with basic structure"""
    
    # This is a minimal report with just a blank page
    # Users will need to add visuals manually in Power BI Desktop
    report = {
        "config": "{}",
        "layoutOptimization": 0,
        "resourcePackages": [
            {
                "resourcePackage": {
                    "name": "SharedResources",
                    "items": []
                }
            }
        ],
        "sections": [
            {
                "name": create_guid(),
                "displayName": "Executive Dashboard",
                "config": "{}",
                "visualContainers": [],
                "height": 720,
                "width": 1280
            },
            {
                "name": create_guid(),
                "displayName": "Rider Analysis",
                "config": "{}",
                "visualContainers": [],
                "height": 720,
                "width": 1280
            },
            {
                "name": create_guid(),
                "displayName": "Horse Analysis",
                "config": "{}",
                "visualContainers": [],
                "height": 720,
                "width": 1280
            },
            {
                "name": create_guid(),
                "displayName": "Trainer Analysis",
                "config": "{}",
                "visualContainers": [],
                "height": 720,
                "width": 1280
            },
            {
                "name": create_guid(),
                "displayName": "Show Analysis",
                "config": "{}",
                "visualContainers": [],
                "height": 720,
                "width": 1280
            },
            {
                "name": create_guid(),
                "displayName": "Trends & Comparisons",
                "config": "{}",
                "visualContainers": [],
                "height": 720,
                "width": 1280
            }
        ]
    }
    
    report_path = report_dir / "report.json"
    with open(report_path, 'w') as f:
        json.dump(report, f, indent=2)
    print(f"[OK] Created {report_path}")

def create_report_platform(report_dir):
    """Create report .platform file"""
    platform = {
        "$schema": "https://developer.microsoft.com/json-schemas/fabric/item/report/definition/visualContainer/1.0.0/schema.json",
        "config": {
            "version": "5.45",
            "themeCollection": {
                "baseTheme": {
                    "name": "CY24SU06"
                }
            }
        },
        "settings": {
            "useNewFilterPaneExperience": True,
            "useStylableVisualContainerHeader": True
        },
        "metadata": {
            "contentType": 7
        }
    }
    
    platform_path = report_dir / ".platform"
    with open(platform_path, 'w') as f:
        json.dump(platform, f, indent=2)
    print(f"[OK] Created {platform_path}")

def create_semantic_model_definition(model_dir):
    """Create semantic model definition.pbism"""
    definition = {
        "version": "1.0",
        "settings": {
            "contentType": 2
        }
    }
    
    def_path = model_dir / "definition.pbism"
    with open(def_path, 'w') as f:
        json.dump(definition, f, indent=2)
    print(f"[OK] Created {def_path}")

def create_model_platform(model_dir):
    """Create semantic model .platform file"""
    platform = {
        "$schema": "https://developer.microsoft.com/json-schemas/fabric/item/dataset/definition/semanticModel/1.0.0/schema.json",
        "config": {
            "version": "5.45",
            "compatibilityLevel": 1604
        },
        "settings": {
            "contentType": 2
        }
    }
    
    platform_path = model_dir / ".platform"
    with open(platform_path, 'w') as f:
        json.dump(platform, f, indent=2)
    print(f"[OK] Created {platform_path}")

def main():
    print("=" * 60)
    print("HorseShows Power BI Report Builder")
    print("=" * 60)
    print()
    
    # Create directory structure
    print("Creating directory structure...")
    base_dir, report_dir, model_dir = create_directory_structure()
    
    # Create .pbip file
    print("\nCreating Power BI project files...")
    create_pbip_file(base_dir)
    
    # Create report files
    create_report_definition(report_dir)
    create_minimal_report_json(report_dir)
    create_report_platform(report_dir)
    
    # Create semantic model files
    create_semantic_model_definition(model_dir)
    create_model_platform(model_dir)
    
    # Copy existing model.bim
    print("\nNOTE: Using existing model.bim file")
    
    print("\n" + "=" * 60)
    print("[SUCCESS] Power BI project created successfully!")
    print("=" * 60)
    print()
    print("NEXT STEPS:")
    print("1. Open HorseShows.pbip in Power BI Desktop")
    print("2. The data model is already configured with:")
    print("   - 7 tables (dimensions and fact table)")
    print("   - All relationships")
    print("   - 17 DAX measures")
    print("3. Add visuals to the 6 blank pages using:")
    print("   - 05_Visual_Recipes.md (step-by-step instructions)")
    print("   - 04_Report_Design.md (layout guidelines)")
    print()
    print("The report will open with blank pages ready for you to")
    print("drag and drop fields to create visuals.")
    print()

if __name__ == "__main__":
    main()
