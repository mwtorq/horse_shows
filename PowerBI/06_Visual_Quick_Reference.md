# Power BI Visual Quick Reference

## Common Visual Types & How to Build Them

### 1. CARD (Single Number)
**When to use**: Show one important metric

**How to build**:
1. Click "Card" visual in Visualizations pane
2. Drag measure to "Fields" bucket
3. Format:
   - General > Title: On (add description)
   - Call out value > Display units: Auto
   - Category label: Off (unless you want it)

**Example**: Total Shows card
- Fields: `_Measures[Total Shows]`

---

### 2. TABLE (Data Grid)
**When to use**: Show detailed records with multiple columns

**How to build**:
1. Click "Table" visual
2. Drag dimensions and measures to "Columns" bucket (order matters!)
3. Format:
   - Style: Minimal or Alternating rows
   - Conditional formatting: Right-click column > Conditional formatting
   - Sort: Click column header in preview

**Example**: Rider Leaderboard
- Columns (in order):
  1. `dimRiders[RiderName]`
  2. `_Measures[Total Entries]`
  3. `_Measures[First Places]`
  4. `_Measures[Placement Rate %]`
- Conditional Format: Placement Rate % > Data bars

---

### 3. BAR CHART (Compare Categories)
**When to use**: Compare values across categories

**How to build**:
1. Click "Clustered bar chart" visual
2. Drag dimension to "Y-axis" bucket
3. Drag measure(s) to "X-axis" bucket
4. Optional: Drag dimension to "Legend" for stacking
5. Format:
   - Data labels: On (if space allows)
   - Sort: Click "..." > Sort by > Choose measure

**Example**: Top 10 Shows
- Y-axis: `dimShows[ShowName]`
- X-axis: `_Measures[Total Entries]`
- Filters: Top 10 by Total Entries

---

### 4. LINE CHART (Trends Over Time)
**When to use**: Show changes over time

**How to build**:
1. Click "Line chart" visual
2. Drag date dimension to "X-axis" bucket
3. Drag measure(s) to "Y-axis" bucket
4. Optional: Drag dimension to "Legend" to show multiple lines
5. Format:
   - Markers: On (for clarity)
   - Data labels: Auto (only at key points)

**Example**: Entries by Month
- X-axis: `dimDate[MonthName]` (sort by `dimDate[MonthNum]`)
- Y-axis: `_Measures[Total Entries]`
- Legend: `dimShows[Year]`

---

### 5. DONUT/PIE CHART (Parts of Whole)
**When to use**: Show composition/breakdown (max 5-7 categories)

**How to build**:
1. Click "Donut chart" visual
2. Drag dimension to "Legend" bucket
3. Drag measure to "Values" bucket
4. Format:
   - Detail labels: Category and value
   - Legend: Right side
   - Slices: Sort by value (descending)

**Example**: Placements vs Non-Placing
- Legend: `factResults[Placement Status]`
- Values: `_Measures[Total Entries]`

---

### 6. SLICER (Filter Control)
**When to use**: Let users filter the entire page or report

**How to build**:
1. Click "Slicer" visual
2. Drag dimension to "Field" bucket
3. Format:
   - Slicer settings > Style: Dropdown (saves space)
   - Search: On (for long lists)
   - Select all: On
4. Set interaction:
   - Format > Edit interactions
   - Choose which visuals it affects

**Example**: Rider Search
- Field: `dimRiders[RiderName]`
- Style: Dropdown with search

---

### 7. MATRIX (Cross-Tab/Pivot Table)
**When to use**: Compare two dimensions (heatmap)

**How to build**:
1. Click "Matrix" visual
2. Drag first dimension to "Rows" bucket
3. Drag second dimension to "Columns" bucket
4. Drag measure to "Values" bucket
5. Format:
   - Values > Background color: Conditional formatting (heatmap)
   - Subtotals: Off (usually)
   - +/- icons: Show

**Example**: State x Year Heatmap
- Rows: `dimShows[StateProv]`
- Columns: `dimShows[Year]`
- Values: `_Measures[Total Entries]`
- Conditional Format: Background color gradient

---

### 8. MULTI-ROW CARD (Multiple Metrics)
**When to use**: Show related metrics together

**How to build**:
1. Click "Multi-row card" visual
2. Drag multiple measures to "Fields" bucket
3. Format:
   - Data labels: Customize labels
   - Card layout: Spacing

**Example**: Show Stats
- Fields:
  - `_Measures[Total Classes]`
  - `_Measures[Total Entries]`
  - `dimShows[StartDate]`
  - `dimShows[EndDate]`

---

### 9. STACKED BAR CHART (Multiple Series)
**When to use**: Compare categories with sub-categories

**How to build**:
1. Click "Stacked bar chart" visual
2. Drag dimension to "Axis" bucket
3. Drag MULTIPLE measures to "Values" bucket
4. Format:
   - Legend: Bottom (easier to read)
   - Data labels: Off (too cluttered)

**Example**: Rider by Class Type
- Axis: `dimClasses[ClassType]`
- Values: 
  - `_Measures[First Places]`
  - `_Measures[Top 3 Places]`
  - `_Measures[Total Entries]`

---

### 10. TREEMAP (Hierarchical Breakdown)
**When to use**: Show relative sizes with space-filling layout

**How to build**:
1. Click "Treemap" visual
2. Drag dimension to "Category" bucket
3. Drag measure to "Values" bucket
4. Format:
   - Data labels: Category and value
   - Colors: By category

**Example**: Trainer's Riders
- Category: `dimRiders[RiderName]`
- Values: `_Measures[First Places]`
- Filter: Selected trainer only

---

## Pro Tips

### Conditional Formatting
1. Select visual > Values bucket > Right-click measure
2. Choose: Background color, Font color, or Data bars
3. Format by: Rules (gradient) or Field value

### Sorting
- Click "..." menu on visual > Sort by > Choose field
- Or click column headers in preview mode

### Filtering
- Filters pane (right side):
  - Visual level: Just this visual
  - Page level: Entire page
  - Report level: All pages
- Use "Top N" filter for leaderboards

### Interactions
- Select a visual > Format > Edit interactions
- Choose: Filter (funnel), Highlight (target), or None (X)
- Disable interactions between unrelated visuals

### Performance
- Use Import mode (not DirectQuery)
- Minimize calculated columns (use measures instead)
- Limit visuals per page (max 10-15)

---

## Common Patterns

### KPI Row
- 3-5 cards across the top showing key numbers
- Same height, evenly spaced
- Use contrasting background colors

### Leaderboard
- Table with 5-8 columns
- Sort by main metric (desc)
- Add conditional formatting for easy scanning
- Consider Top N filter

### Time Trend
- Line chart with date on X-axis
- Multiple lines for comparison
- Add forecast if appropriate

### Filter Bar
- 2-5 slicers across top or left side
- Use dropdown style to save space
- Add "Clear all" bookmark

---

**Need more help?** Open `05_Visual_Recipes.md` for specific examples!
