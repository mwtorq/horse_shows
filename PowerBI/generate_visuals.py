"""
Power BI Visual Generator
Generates actual Power BI visuals from the Visual Recipes
"""

import json
import uuid
from pathlib import Path

def create_guid():
    """Generate a new GUID"""
    return str(uuid.uuid4())

def create_card_visual(title, measure_name, x, y, width, height, z_index):
    """Create a card visual"""
    return {
        "x": x,
        "y": y,
        "z": z_index,
        "width": width,
        "height": height,
        "config": json.dumps({
            "name": create_guid(),
            "layouts": [
                {
                    "id": 0,
                    "position": {
                        "x": x,
                        "y": y,
                        "z": z_index,
                        "width": width,
                        "height": height
                    }
                }
            ],
            "singleVisual": {
                "visualType": "card",
                "projections": {
                    "Values": [
                        {
                            "queryRef": f"{measure_name}"
                        }
                    ]
                },
                "prototypeQuery": {
                    "Version": 2,
                    "From": [
                        {
                            "Name": "_Measures",
                            "Entity": "_Measures"
                        }
                    ],
                    "Select": [
                        {
                            "Measure": {
                                "Expression": {
                                    "SourceRef": {
                                        "Source": "_Measures"
                                    }
                                },
                                "Property": measure_name
                            },
                            "Name": f"_Measures.{measure_name}"
                        }
                    ]
                },
                "vcObjects": {
                    "title": [
                        {
                            "properties": {
                                "text": {
                                    "expr": {
                                        "Literal": {
                                            "Value": f"'{title}'"
                                        }
                                    }
                                },
                                "show": {
                                    "expr": {
                                        "Literal": {
                                            "Value": "true"
                                        }
                                    }
                                }
                            }
                        }
                    ]
                }
            }
        })
    }

def create_table_visual(title, columns, x, y, width, height, z_index):
    """Create a table visual with multiple columns"""
    projections = []
    select_items = []
    
    for col in columns:
        table_name = col['table']
        column_name = col['column']
        
        projections.append({
            "queryRef": f"{table_name}.{column_name}"
        })
        
        if col.get('is_measure', False):
            select_items.append({
                "Measure": {
                    "Expression": {
                        "SourceRef": {
                            "Source": table_name
                        }
                    },
                    "Property": column_name
                },
                "Name": f"{table_name}.{column_name}"
            })
        else:
            select_items.append({
                "Column": {
                    "Expression": {
                        "SourceRef": {
                            "Source": table_name
                        }
                    },
                    "Property": column_name
                },
                "Name": f"{table_name}.{column_name}"
            })
    
    return {
        "x": x,
        "y": y,
        "z": z_index,
        "width": width,
        "height": height,
        "config": json.dumps({
            "name": create_guid(),
            "layouts": [
                {
                    "id": 0,
                    "position": {
                        "x": x,
                        "y": y,
                        "z": z_index,
                        "width": width,
                        "height": height
                    }
                }
            ],
            "singleVisual": {
                "visualType": "tableEx",
                "projections": {
                    "Values": projections
                },
                "prototypeQuery": {
                    "Version": 2,
                    "From": [{"Name": col['table'], "Entity": col['table']} for col in columns],
                    "Select": select_items
                },
                "vcObjects": {
                    "title": [
                        {
                            "properties": {
                                "text": {
                                    "expr": {
                                        "Literal": {
                                            "Value": f"'{title}'"
                                        }
                                    }
                                },
                                "show": {
                                    "expr": {
                                        "Literal": {
                                            "Value": "true"
                                        }
                                    }
                                }
                            }
                        }
                    ],
                    "grid": [
                        {
                            "properties": {
                                "gridVertical": {
                                    "expr": {
                                        "Literal": {
                                            "Value": "true"
                                        }
                                    }
                                },
                                "gridHorizontal": {
                                    "expr": {
                                        "Literal": {
                                            "Value": "true"
                                        }
                                    }
                                }
                            }
                        }
                    ]
                }
            }
        })
    }

def create_bar_chart_visual(title, axis_table, axis_column, value_measure, x, y, width, height, z_index):
    """Create a clustered bar chart"""
    return {
        "x": x,
        "y": y,
        "z": z_index,
        "width": width,
        "height": height,
        "config": json.dumps({
            "name": create_guid(),
            "layouts": [
                {
                    "id": 0,
                    "position": {
                        "x": x,
                        "y": y,
                        "z": z_index,
                        "width": width,
                        "height": height
                    }
                }
            ],
            "singleVisual": {
                "visualType": "barChart",
                "projections": {
                    "Category": [
                        {
                            "queryRef": f"{axis_table}.{axis_column}"
                        }
                    ],
                    "Y": [
                        {
                            "queryRef": f"_Measures.{value_measure}"
                        }
                    ]
                },
                "prototypeQuery": {
                    "Version": 2,
                    "From": [
                        {"Name": axis_table, "Entity": axis_table},
                        {"Name": "_Measures", "Entity": "_Measures"}
                    ],
                    "Select": [
                        {
                            "Column": {
                                "Expression": {"SourceRef": {"Source": axis_table}},
                                "Property": axis_column
                            },
                            "Name": f"{axis_table}.{axis_column}"
                        },
                        {
                            "Measure": {
                                "Expression": {"SourceRef": {"Source": "_Measures"}},
                                "Property": value_measure
                            },
                            "Name": f"_Measures.{value_measure}"
                        }
                    ]
                },
                "vcObjects": {
                    "title": [
                        {
                            "properties": {
                                "text": {
                                    "expr": {
                                        "Literal": {
                                            "Value": f"'{title}'"
                                        }
                                    }
                                },
                                "show": {
                                    "expr": {
                                        "Literal": {
                                            "Value": "true"
                                        }
                                    }
                                }
                            }
                        }
                    ]
                }
            }
        })
    }

def create_line_chart_visual(title, x_axis_table, x_axis_column, y_measure, legend_table, legend_column, x, y, width, height, z_index):
    """Create a line chart"""
    return {
        "x": x,
        "y": y,
        "z": z_index,
        "width": width,
        "height": height,
        "config": json.dumps({
            "name": create_guid(),
            "layouts": [
                {
                    "id": 0,
                    "position": {
                        "x": x,
                        "y": y,
                        "z": z_index,
                        "width": width,
                        "height": height
                    }
                }
            ],
            "singleVisual": {
                "visualType": "lineChart",
                "projections": {
                    "Category": [
                        {
                            "queryRef": f"{x_axis_table}.{x_axis_column}"
                        }
                    ],
                    "Y": [
                        {
                            "queryRef": f"_Measures.{y_measure}"
                        }
                    ],
                    "Series": [
                        {
                            "queryRef": f"{legend_table}.{legend_column}"
                        }
                    ]
                },
                "prototypeQuery": {
                    "Version": 2,
                    "From": [
                        {"Name": x_axis_table, "Entity": x_axis_table},
                        {"Name": legend_table, "Entity": legend_table},
                        {"Name": "_Measures", "Entity": "_Measures"}
                    ],
                    "Select": [
                        {
                            "Column": {
                                "Expression": {"SourceRef": {"Source": x_axis_table}},
                                "Property": x_axis_column
                            },
                            "Name": f"{x_axis_table}.{x_axis_column}"
                        },
                        {
                            "Column": {
                                "Expression": {"SourceRef": {"Source": legend_table}},
                                "Property": legend_column
                            },
                            "Name": f"{legend_table}.{legend_column}"
                        },
                        {
                            "Measure": {
                                "Expression": {"SourceRef": {"Source": "_Measures"}},
                                "Property": y_measure
                            },
                            "Name": f"_Measures.{y_measure}"
                        }
                    ]
                },
                "vcObjects": {
                    "title": [
                        {
                            "properties": {
                                "text": {
                                    "expr": {
                                        "Literal": {
                                            "Value": f"'{title}'"
                                        }
                                    }
                                },
                                "show": {
                                    "expr": {
                                        "Literal": {
                                            "Value": "true"
                                        }
                                    }
                                }
                            }
                        }
                    ]
                }
            }
        })
    }

def create_slicer_visual(title, table, column, x, y, width, height, z_index):
    """Create a slicer visual"""
    return {
        "x": x,
        "y": y,
        "z": z_index,
        "width": width,
        "height": height,
        "config": json.dumps({
            "name": create_guid(),
            "layouts": [
                {
                    "id": 0,
                    "position": {
                        "x": x,
                        "y": y,
                        "z": z_index,
                        "width": width,
                        "height": height
                    }
                }
            ],
            "singleVisual": {
                "visualType": "slicer",
                "projections": {
                    "Values": [
                        {
                            "queryRef": f"{table}.{column}"
                        }
                    ]
                },
                "prototypeQuery": {
                    "Version": 2,
                    "From": [
                        {"Name": table, "Entity": table}
                    ],
                    "Select": [
                        {
                            "Column": {
                                "Expression": {"SourceRef": {"Source": table}},
                                "Property": column
                            },
                            "Name": f"{table}.{column}"
                        }
                    ]
                },
                "vcObjects": {
                    "title": [
                        {
                            "properties": {
                                "text": {
                                    "expr": {
                                        "Literal": {
                                            "Value": f"'{title}'"
                                        }
                                    }
                                },
                                "show": {
                                    "expr": {
                                        "Literal": {
                                            "Value": "true"
                                        }
                                    }
                                }
                            }
                        }
                    ]
                }
            }
        })
    }

def create_page_1_executive_dashboard():
    """Create visuals for Page 1: Executive Dashboard"""
    visuals = []
    
    # Row 1: KPI Cards (4 cards across top)
    card_width = 300
    card_height = 120
    card_y = 10
    spacing = 20
    
    # Card 1: Total Shows
    visuals.append(create_card_visual("Total Shows", "Total Shows", 10, card_y, card_width, card_height, 1000))
    
    # Card 2: Total Entries
    visuals.append(create_card_visual("Total Entries", "Total Entries", 10 + card_width + spacing, card_y, card_width, card_height, 1001))
    
    # Card 3: First Places
    visuals.append(create_card_visual("First Places", "First Places", 10 + (card_width + spacing) * 2, card_y, card_width, card_height, 1002))
    
    # Card 4: Prize Money
    visuals.append(create_card_visual("Total Prize Money", "Total Prize Money", 10 + (card_width + spacing) * 3, card_y, card_width, card_height, 1003))
    
    # Row 2: Line Chart - Entries by Month
    visuals.append(create_line_chart_visual(
        "Entries by Month",
        "dimDate", "MonthName",
        "Total Entries",
        "dimShows", "Year",
        10, 150, 1260, 250, 1004
    ))
    
    # Row 3: Two charts side by side
    # Bar Chart: Top 10 Shows
    visuals.append(create_bar_chart_visual(
        "Top 10 Shows by Entries",
        "dimShows", "ShowName",
        "Total Entries",
        10, 420, 620, 290, 1005
    ))
    
    return visuals

def create_page_2_rider_analysis():
    """Create visuals for Page 2: Rider Analysis"""
    visuals = []
    
    # Slicers at top
    visuals.append(create_slicer_visual("Select Rider", "dimRiders", "RiderName", 10, 10, 300, 80, 2000))
    visuals.append(create_slicer_visual("Select Year", "dimShows", "Year", 330, 10, 150, 80, 2001))
    
    # Rider Leaderboard Table
    rider_columns = [
        {"table": "dimRiders", "column": "RiderName", "is_measure": False},
        {"table": "_Measures", "column": "Total Entries", "is_measure": True},
        {"table": "_Measures", "column": "First Places", "is_measure": True},
        {"table": "_Measures", "column": "Top 3 Places", "is_measure": True},
        {"table": "_Measures", "column": "Placement Rate %", "is_measure": True},
        {"table": "_Measures", "column": "Total Prize Money", "is_measure": True}
    ]
    
    visuals.append(create_table_visual(
        "Rider Leaderboard",
        rider_columns,
        10, 110, 1260, 600, 2002
    ))
    
    return visuals

def create_page_3_horse_analysis():
    """Create visuals for Page 3: Horse Analysis"""
    visuals = []
    
    # Slicers
    visuals.append(create_slicer_visual("Select Horse", "dimHorses", "HorseName", 10, 10, 300, 80, 3000))
    visuals.append(create_slicer_visual("Select Owner", "dimHorses", "OwnerName", 330, 10, 300, 80, 3001))
    
    # Horse Leaderboard
    horse_columns = [
        {"table": "dimHorses", "column": "HorseName", "is_measure": False},
        {"table": "dimHorses", "column": "OwnerName", "is_measure": False},
        {"table": "_Measures", "column": "Total Entries", "is_measure": True},
        {"table": "_Measures", "column": "First Places", "is_measure": True},
        {"table": "_Measures", "column": "Top 3 Places", "is_measure": True},
        {"table": "_Measures", "column": "Placement Rate %", "is_measure": True}
    ]
    
    visuals.append(create_table_visual(
        "Horse Leaderboard",
        horse_columns,
        10, 110, 1260, 600, 3002
    ))
    
    return visuals

def create_page_4_trainer_analysis():
    """Create visuals for Page 4: Trainer Analysis"""
    visuals = []
    
    # Slicer
    visuals.append(create_slicer_visual("Select Trainer", "dimTrainers", "TrainerName", 10, 10, 400, 80, 4000))
    
    # Trainer Leaderboard
    trainer_columns = [
        {"table": "dimTrainers", "column": "TrainerName", "is_measure": False},
        {"table": "_Measures", "column": "Unique Riders", "is_measure": True},
        {"table": "_Measures", "column": "Unique Horses", "is_measure": True},
        {"table": "_Measures", "column": "First Places", "is_measure": True},
        {"table": "_Measures", "column": "Placement Rate %", "is_measure": True},
        {"table": "_Measures", "column": "Total Prize Money", "is_measure": True}
    ]
    
    visuals.append(create_table_visual(
        "Trainer Leaderboard",
        trainer_columns,
        10, 110, 1260, 600, 4001
    ))
    
    return visuals

def create_page_5_show_analysis():
    """Create visuals for Page 5: Show Analysis"""
    visuals = []
    
    # Slicers
    visuals.append(create_slicer_visual("Select Show", "dimShows", "ShowName", 10, 10, 400, 80, 5000))
    visuals.append(create_slicer_visual("Select Division", "dimClasses", "DivisionName", 430, 10, 300, 80, 5001))
    
    # Class Results Table
    class_columns = [
        {"table": "dimClasses", "column": "ClassNumber", "is_measure": False},
        {"table": "dimClasses", "column": "ClassName", "is_measure": False},
        {"table": "dimClasses", "column": "DivisionName", "is_measure": False},
        {"table": "dimClasses", "column": "TotalEntries", "is_measure": False}
    ]
    
    visuals.append(create_table_visual(
        "Class Results",
        class_columns,
        10, 110, 1260, 600, 5002
    ))
    
    return visuals

def create_page_6_trends():
    """Create visuals for Page 6: Trends & Comparisons"""
    visuals = []
    
    # Slicers
    visuals.append(create_slicer_visual("Select Year", "dimShows", "Year", 10, 10, 200, 80, 6000))
    visuals.append(create_slicer_visual("Select State", "dimShows", "StateProv", 230, 10, 200, 80, 6001))
    
    # YoY Bar Chart
    visuals.append(create_bar_chart_visual(
        "Year Over Year Comparison",
        "dimShows", "Year",
        "Total Entries",
        10, 110, 1260, 600, 6002
    ))
    
    return visuals

def main():
    print("=" * 60)
    print("Power BI Visual Generator")
    print("=" * 60)
    print()
    
    # Read existing report.json
    base_dir = Path(__file__).parent
    report_path = base_dir / "HorseShows.Report" / "report.json"
    
    print(f"Reading {report_path}...")
    with open(report_path, 'r') as f:
        report = json.load(f)
    
    print("Generating visuals...")
    
    # Create visuals for each page
    page_configs = [
        ("Executive Dashboard", create_page_1_executive_dashboard()),
        ("Rider Analysis", create_page_2_rider_analysis()),
        ("Horse Analysis", create_page_3_horse_analysis()),
        ("Trainer Analysis", create_page_4_trainer_analysis()),
        ("Show Analysis", create_page_5_show_analysis()),
        ("Trends & Comparisons", create_page_6_trends())
    ]
    
    # Update each section with visuals
    for idx, (page_name, visuals) in enumerate(page_configs):
        if idx < len(report['sections']):
            report['sections'][idx]['visualContainers'] = visuals
            print(f"  Added {len(visuals)} visuals to '{page_name}'")
    
    # Save updated report
    print(f"\nSaving updated report to {report_path}...")
    with open(report_path, 'w') as f:
        json.dump(report, f, indent=2)
    
    print("\n" + "=" * 60)
    print("[SUCCESS] Visuals generated successfully!")
    print("=" * 60)
    print()
    print("NEXT STEPS:")
    print("1. Open HorseShows.pbip in Power BI Desktop")
    print("2. The report now has pre-built visuals on all 6 pages")
    print("3. You may need to:")
    print("   - Adjust visual positions and sizes")
    print("   - Apply formatting and colors")
    print("   - Configure interactions between visuals")
    print()
    print("Note: Power BI may prompt you to refresh the data model")
    print("when you first open the report.")
    print()

if __name__ == "__main__":
    main()
