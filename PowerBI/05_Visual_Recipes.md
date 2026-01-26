# Quick Visual Recipes for HorseShows Power BI Report

## Page 1: Executive Dashboard

### Card 1: Total Shows
- Visual: **Card**
- Field: `_Measures[Total Shows]`
- Position: Top left

### Card 2: Total Entries
- Visual: **Card**
- Field: `_Measures[Total Entries]`
- Position: Top, second from left

### Card 3: First Places
- Visual: **Card**
- Field: `_Measures[First Places]`
- Position: Top, third from left

### Card 4: Prize Money
- Visual: **Card**
- Field: `_Measures[Total Prize Money]`
- Format: Currency
- Position: Top right

### Line Chart: Entries by Month
- Visual: **Line Chart**
- X-Axis: `dimDate[MonthName]` (sort by `dimDate[MonthNum]`)
- Y-Axis: `_Measures[Total Entries]`
- Legend: `dimShows[Year]`
- Position: Middle, full width

### Donut Chart: Placements vs Non-Placing
- Visual: **Donut Chart**
- Legend: Create calculated column: `Placement Status = IF(factResults[Place] > 0, "Placing", "Non-Placing")`
- Values: `_Measures[Total Entries]`
- Position: Bottom left

### Bar Chart: Top 10 Shows
- Visual: **Clustered Bar Chart**
- Axis: `dimShows[ShowName]`
- Values: `_Measures[Total Entries]`
- Filters: Top 10 by Total Entries
- Position: Bottom right

---

## Page 2: Rider Analysis

### Slicer: Rider Search
- Visual: **Slicer**
- Field: `dimRiders[RiderName]`
- Style: Dropdown with search
- Position: Top left

### Slicer: Year
- Visual: **Slicer**
- Field: `dimShows[Year]`
- Style: Dropdown
- Position: Top middle

### Table: Rider Leaderboard
- Visual: **Table**
- Columns:
  1. `dimRiders[RiderName]`
  2. `_Measures[Total Entries]`
  3. `_Measures[First Places]`
  4. `_Measures[Top 3 Places]`
  5. `_Measures[Placement Rate %]`
  6. `_Measures[Total Prize Money]`
- Conditional Formatting:
  - Placement Rate %: Data bars (green gradient)
  - Prize Money: Currency format
- Sort: By First Places (descending)
- Position: Top, full width below slicers

### Stacked Bar Chart: By Class Type
- Visual: **Stacked Bar Chart**
- Axis: `dimClasses[ClassType]`
- Values: `_Measures[First Places]`, `_Measures[Top 3 Places]`, `_Measures[Total Entries]`
- Filters: Selected rider only
- Position: Bottom left

### Line Chart: Performance Over Time
- Visual: **Line Chart**
- X-Axis: `dimDate[Date]` (by month)
- Y-Axis: `_Measures[Placement Rate %]`
- Position: Bottom right

---

## Page 3: Horse Analysis

### Slicer: Horse Search
- Visual: **Slicer**
- Field: `dimHorses[HorseName]`
- Style: Dropdown with search

### Slicer: Owner
- Visual: **Slicer**
- Field: `dimHorses[OwnerName]`
- Style: Dropdown

### Table: Horse Leaderboard
- Visual: **Table**
- Columns:
  1. `dimHorses[HorseName]`
  2. `dimHorses[OwnerName]`
  3. `_Measures[Total Entries]`
  4. `_Measures[First Places]`
  5. `_Measures[Top 3 Places]`
  6. `_Measures[Placement Rate %]`
- Conditional Formatting: Same as Rider table

### Stacked Bar: By Division
- Visual: **Stacked Bar Chart**
- Axis: `dimClasses[DivisionName]`
- Values: `_Measures[First Places]`, `_Measures[Top 3 Places]`

### Table: Show History
- Visual: **Table**
- Columns:
  1. `dimShows[ShowName]`
  2. `dimShows[StartDate]`
  3. `dimClasses[ClassName]`
  4. `factResults[Place]`
  5. `factResults[PrizeMoney]`
- Filters: Selected horse only

---

## Page 4: Trainer Analysis

### Slicer: Trainer Search
- Visual: **Slicer**
- Field: `dimTrainers[TrainerName]`

### Table: Trainer Leaderboard
- Visual: **Table**
- Columns:
  1. `dimTrainers[TrainerName]`
  2. `_Measures[Unique Riders]`
  3. `_Measures[Unique Horses]`
  4. `_Measures[First Places]`
  5. `_Measures[Placement Rate %]`
  6. `_Measures[Total Prize Money]`

### Treemap: Trainer's Riders
- Visual: **Treemap**
- Category: `dimRiders[RiderName]`
- Values: `_Measures[First Places]`
- Filters: Selected trainer only

### Bar Chart: By Division
- Visual: **Clustered Bar**
- Axis: `dimClasses[DivisionName]`
- Values: `_Measures[Total Placements]`

---

## Page 5: Show Analysis

### Slicer: Show
- Visual: **Slicer**
- Field: `dimShows[ShowName]`
- Style: Dropdown

### Slicer: Division
- Visual: **Slicer**
- Field: `dimClasses[DivisionName]`

### Card: Show Dates
- Visual: **Multi-row Card**
- Fields: `dimShows[StartDate]`, `dimShows[EndDate]`, `dimShows[ShowLocation]`

### Card: Stats
- Visual: **Multi-row Card**
- Fields: `_Measures[Total Classes]`, `_Measures[Total Entries]`

### Table: Class Results
- Visual: **Table**
- Columns:
  1. `dimClasses[ClassNumber]`
  2. `dimClasses[ClassName]`
  3. `dimClasses[DivisionName]`
  4. `dimClasses[TotalEntries]`
  5. First place rider (needs calculated column)

### Bar Chart: By Division
- Visual: **Clustered Bar**
- Axis: `dimClasses[DivisionName]`
- Values: `_Measures[Total Entries]`

---

## Page 6: Trends & Comparisons

### Slicer: Year Range
- Visual: **Slicer**
- Field: `dimShows[Year]`
- Style: Between (range selector)

### Slicer: States
- Visual: **Slicer**
- Field: `dimShows[StateProv]`
- Style: Multi-select list

### Line Chart: Participation Trends
- Visual: **Line Chart**
- X-Axis: `dimDate[Date]` (by year)
- Y-Axis: Multiple measures
  - `_Measures[Total Shows]`
  - `_Measures[Total Entries]`
  - `_Measures[Unique Riders]`
- Legend: Measure name

### Clustered Bar: YoY Comparison
- Visual: **Clustered Bar Chart**
- Axis: `dimShows[Year]`
- Values: `_Measures[Total Entries]`, `_Measures[Total Shows]`

### Matrix: State x Year Heatmap
- Visual: **Matrix**
- Rows: `dimShows[StateProv]`
- Columns: `dimShows[Year]`
- Values: `_Measures[Total Entries]`
- Conditional Formatting: Background color (heat map)

---

## Pro Tips

### Formatting
1. **Theme**: File > Options > Report Settings > Choose a theme
2. **Page Size**: View tab > Page size > 16:9 (recommended)
3. **Background**: Format pane > Page background (light gray works well)

### Interactions
1. Select a visual > Format > Edit interactions
2. Disable cross-filtering between unrelated visuals

### Bookmarks
1. View tab > Bookmarks > Add
2. Create bookmarks for:
   - Reset All Filters
   - Current Year Only
   - Top Performers

### Performance
1. Don't use too many visuals per page (max 10-15)
2. Use summary tables for large datasets
3. Limit visual interactions
4. Use Import mode (not DirectQuery) for faster performance
