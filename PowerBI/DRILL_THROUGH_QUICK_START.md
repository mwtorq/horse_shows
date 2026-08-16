# Quick Drill-Through Setup for Power BI

## The file is currently locked (Power BI or OneDrive is using it)

### Option 1: Manual Setup (Recommended - 5 minutes)

**Close Power BI Desktop first**, then follow these steps:

#### For Rider Analysis Page:
1. Open Power BI Desktop → Open `HorseShows.pbip`
2. Navigate to **Rider Analysis** page
3. Click on **blank canvas** (not on any visual)
4. In the **Visualizations pane** (right side), find **Drill through** section
5. From the **Fields pane**, drag `dimRiders[RiderName]` into the **Drill-through fields** box
6. A back arrow button will automatically appear on the page

#### For Horse Analysis Page:
1. Navigate to **Horse Analysis** page  
2. Click blank canvas
3. Drag `dimHorses[HorseName]` to **Drill-through fields**
4. Back button appears automatically

#### For Trainer Analysis Page:
1. Navigate to **Trainer Analysis** page
2. Click blank canvas  
3. Drag `dimTrainers[TrainerName]` to **Drill-through fields**
4. Back button appears automatically

**Save the report** (Ctrl+S)

---

### Option 2: Run the Script (When file is available)

1. **Close Power BI Desktop completely**
2. **Wait for OneDrive sync** to complete (check system tray)
3. Run this command:

```bash
cd "c:\Users\mw\OneDrive - timberwilde.net\repos\horse_shows\PowerBI"
python add_drill_through.py
```

4. Open `HorseShows.pbip` to see the drill-through enabled

---

## How to Test It Works

1. Open the report in Power BI Desktop
2. Click **View** tab → **Reading View** (or press Alt+F5)
3. On the Executive Dashboard page, **right-click** on any rider name
4. You should see **"Drill through" > "Rider Analysis"** in the menu
5. Click it - you'll navigate to Rider Analysis filtered to that rider
6. Click the **back arrow** to return

---

## What Users Will See

### Example Flow:
```
Executive Dashboard (showing all riders)
  ↓ (user right-clicks "SMITH, JOHN")
  ↓ (selects "Drill through > Rider Analysis")
  ↓
Rider Analysis Page (filtered to SMITH, JOHN only)
  ← (back button to return)
```

### Works from ANY page:
- Right-click a rider name → Drill to Rider Analysis
- Right-click a horse name → Drill to Horse Analysis  
- Right-click a trainer name → Drill to Trainer Analysis

---

## Why This is Powerful

✅ **Self-Service**: Users explore data without your help  
✅ **Contextual**: See overview, drill into details naturally  
✅ **Fast**: One right-click instead of manual filtering  
✅ **Professional**: Standard Power BI UX pattern  
✅ **Maintainable**: One page serves all riders/horses/trainers

---

## Need Help?

See the full guide: `07_Drill_Through_Setup.md`

The documentation includes:
- Step-by-step screenshots walkthrough
- Troubleshooting common issues  
- Customizing the back button
- Testing procedures
- Advanced scenarios
