# HorseShows Power BI Report Design Guide

## Overview
This document describes the recommended layout and configuration for the HorseShows Power BI report.

## Setup Instructions

### 1. Create the Database Views
Run `01_PowerBI_Views.sql` against your HorseShows database to create the optimized views.

### 2. Connect Power BI to Data
1. Open Power BI Desktop
2. Get Data > SQL Server
3. Enter your server name and database (HorseShows)
4. Select DirectQuery or Import mode (Import recommended for better performance)
5. Select the views:
   - sResults.dimShows
   - sResults.dimClasses
   - sResults.dimRiders
   - sResults.dimHorses
   - sResults.dimTrainers
   - sResults.dimDate
   - sResults.factResults

### 3. Configure Relationships
Create the following relationships in Model view:

| From Table | From Column | To Table | To Column | Cardinality |
|------------|-------------|----------|-----------|-------------|
| factResults | ShowID | dimShows | ShowID | Many-to-One |
| factResults | ClassID | dimClasses | ClassID | Many-to-One |
| factResults | RiderID | dimRiders | RiderID | Many-to-One |
| factResults | HorseID | dimHorses | HorseID | Many-to-One |
| factResults | TrainerID | dimTrainers | TrainerID | Many-to-One |
| factResults | ShowDate | dimDate | Date | Many-to-One |
| dimClasses | ShowID | dimShows | ShowID | Many-to-One |

### 4. Create Measures Table
1. Modeling > New Table
2. Name: "_Measures"
3. Enter: `_Measures = ROW("Placeholder", 0)`
4. Add all DAX measures from `03_DAX_Measures.dax`

---

## Report Pages

### Page 1: Executive Dashboard
**Purpose:** High-level KPIs and trends

**Layout:**
```
┌─────────────────────────────────────────────────────────────┐
│  [Year Slicer]  [State Slicer]  [Show Slicer]              │
├─────────────┬─────────────┬─────────────┬─────────────────┤
│   CARD      │   CARD      │   CARD      │     CARD        │
│ Total Shows │Total Entries│ First Places│ Prize Money     │
├─────────────┴─────────────┴─────────────┴─────────────────┤
│                                                            │
│   LINE CHART: Entries by Month (with Year comparison)     │
│                                                            │
├────────────────────────────┬──────────────────────────────┤
│  DONUT CHART               │  BAR CHART                   │
│  Placements vs Non-Placing │  Top 10 Shows by Entries     │
└────────────────────────────┴──────────────────────────────┘
```

### Page 2: Rider Analysis
**Purpose:** Drill into rider performance

**Layout:**
```
┌─────────────────────────────────────────────────────────────┐
│  [Rider Search Box]  [Year Slicer]  [State Slicer]         │
├─────────────────────────────────────────────────────────────┤
│  TABLE: Rider Leaderboard                                   │
│  Columns: Rider | Entries | 1st | Top 3 | Rate% | Prize$  │
│  (Conditional formatting on Rate%, sortable)                │
├────────────────────────────┬──────────────────────────────┤
│  BAR CHART                 │  LINE CHART                   │
│  Selected Rider by Class   │  Performance Over Time        │
├────────────────────────────┴──────────────────────────────┤
│  TABLE: Rider's Horse/Trainer Combinations                 │
└─────────────────────────────────────────────────────────────┘
```

### Page 3: Horse Analysis
**Purpose:** Drill into horse performance

**Layout:**
```
┌─────────────────────────────────────────────────────────────┐
│  [Horse Search Box]  [Owner Filter]  [Year Slicer]         │
├─────────────────────────────────────────────────────────────┤
│  TABLE: Horse Leaderboard                                   │
│  Columns: Horse | Owner | Entries | 1st | Top 3 | Rate%   │
├────────────────────────────┬──────────────────────────────┤
│  STACKED BAR               │  SCATTER PLOT                 │
│  Placements by Class Type  │  Entries vs Win Rate          │
├────────────────────────────┴──────────────────────────────┤
│  TABLE: Horse's Show History                               │
└─────────────────────────────────────────────────────────────┘
```

### Page 4: Trainer Analysis
**Purpose:** Drill into trainer performance

**Layout:**
```
┌─────────────────────────────────────────────────────────────┐
│  [Trainer Search Box]  [Year Slicer]                        │
├─────────────────────────────────────────────────────────────┤
│  TABLE: Trainer Leaderboard                                 │
│  Columns: Trainer | Riders | Horses | 1st | Rate% | Prize$ │
├────────────────────────────┬──────────────────────────────┤
│  TREEMAP                   │  BAR CHART                    │
│  Trainer's Riders          │  Success by Division          │
└────────────────────────────┴──────────────────────────────┘
```

### Page 5: Show Analysis
**Purpose:** Analyze individual shows

**Layout:**
```
┌─────────────────────────────────────────────────────────────┐
│  [Show Dropdown]  [Year Slicer]  [Division Slicer]         │
├─────────────┬─────────────┬─────────────┬─────────────────┤
│ Show Dates  │ Total Classes│ Total Entries│ Avg Per Class │
├─────────────┴─────────────┴─────────────┴─────────────────┤
│  TABLE: Class Results                                       │
│  Columns: Class | Name | Division | Entries | Winner       │
├────────────────────────────┬──────────────────────────────┤
│  MAP (if location data)    │  BAR: Entries by Division     │
└────────────────────────────┴──────────────────────────────┘
```

### Page 6: Trends & Comparisons
**Purpose:** Year-over-year and trend analysis

**Layout:**
```
┌─────────────────────────────────────────────────────────────┐
│  [Year Range Slicer]  [State Multi-Select]                  │
├─────────────────────────────────────────────────────────────┤
│  LINE CHART: Participation Trends (Shows, Entries, Riders) │
├────────────────────────────┬──────────────────────────────┤
│  CLUSTERED BAR             │  WATERFALL                    │
│  YoY Comparison            │  Growth Contributors          │
├────────────────────────────┴──────────────────────────────┤
│  MATRIX: Year x State Heatmap of Entries                   │
└─────────────────────────────────────────────────────────────┘
```

---

## Slicers (Filters)

### Recommended Slicers for All Pages
- **Year** (dimShows[Year]) - Dropdown or Buttons
- **State/Province** (dimShows[StateProv]) - Multi-select dropdown
- **Show Name** (dimShows[ShowDisplay]) - Searchable dropdown

### Page-Specific Slicers
- **Division** (dimClasses[DivisionName]) - For class analysis
- **Class Type** (dimClasses[ClassType]) - For class analysis
- **Rider** (dimRiders[RiderName]) - For rider pages
- **Trainer** (dimTrainers[TrainerName]) - For trainer pages

---

## Visual Formatting Guidelines

### Colors
- Primary: #1976D2 (Blue)
- Success: #2E7D32 (Green)
- Warning: #F57C00 (Orange)
- Danger: #D32F2F (Red)

### Conditional Formatting
Apply to Placement Rate % columns:
- >= 70%: Green background
- 50-69%: Blue background
- 30-49%: Orange background
- < 30%: Red background

### Data Bars
Use for numeric columns like Entries, First Places, Prize Money

---

## Bookmarks & Navigation

Create bookmarks for:
1. **Reset All Filters** - Clear all slicers
2. **Current Year** - Filter to current year
3. **My Riders** - Pre-filter to specific riders (customize)

Add navigation buttons between pages using Action buttons.

---

## Mobile Layout

Configure mobile layout for Pages 1 & 2:
- Stack cards vertically
- Make slicers collapsible
- Prioritize KPI cards at top
- Single chart per row

---

## Refresh Schedule

If publishing to Power BI Service:
- **Recommended:** Daily refresh at 6 AM
- **Alternative:** Real-time with DirectQuery (higher server load)

---

## Security (Row-Level Security)

Optional: If you need to restrict data by user:

```dax
// Example: Restrict trainers to only see their own data
[TrainerName] = USERPRINCIPALNAME()
```

Create roles in Modeling > Manage Roles.
