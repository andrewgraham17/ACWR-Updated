# K-State Baseball — Throw Log (Streamlit)

There's a tab for each pitcher on the 2026 staff, plus a 🏠 Team tab. Inside each player's tab are five sections:
**Throw Log**, **Dashboard**, **Day Type Templates**, **Next Outing Planner** and **Build-Up Plan**.
**Everything saves automatically**: there are no Save buttons.

## What's new (Fall 2026 workbook update)

- **Smooth distance factor.** In-between distances fall on a straight line between 60, 90, 120, 150, 180 and 210 ft. For example, 75 ft = 1.15 and 135 ft = 1.95.
- **Long toss is one entry.** Enter the farthest distance and the total throws. It's scored as the standard step-out (90, 120, 150 … every 30 ft), with more throws at the short steps.
- **New throw rates** for time-based entries: Long Toss 3.5/min, Compression 3/min, Bullpen 2.5/min, Moderate 4/min, Recovery 5.5/min.
- **Back-to-back mound days.** A Bullpen/Game day the day after another outing is multiplied ×1.5, or ×1.25 with one day in between. It shows in the *B2B ×* column.
- **Day Type Templates** were updated. Low Bullpen is no longer a day type, and the long-toss days show their step split.
- **Dashboard** has a 12-week weekly workload chart and table.
- **Next Outing Planner** plans up to 42 days ahead.
- **Build-Up Plan** (new) lays out every day from first catch play to the first bullpen. Throw counts are solved from the workload model so the ACWR stays in the 0.8–1.3 sweet spot. Each day has *Make off* and *Throws / Distance / Velo override* cells. Griffin Lewis, Stevie Doty, Kaden Dean and Adam Arther have plans loaded from the workbook.

## Make it public, with data that stays saved

On Streamlit Community Cloud, files on the server are wiped every time the app restarts or redeploys. So the public app needs a free hosted database:

1. **Create the database.** Sign up at **neon.tech** (free) and create a project. Copy its connection string, which looks like
   `postgresql://user:password@ep-something.neon.tech/neondb?sslmode=require`.
2. **Update the GitHub repo** that acwr-kstatebaseball.streamlit.app deploys from. Replace its files with the files in this folder, keeping the existing `assets/` folder with the wordmark.
3. **Add the secret.** In Streamlit Cloud, open the app ▸ **Settings ▸ Secrets** and paste:
   `DATABASE_URL = "postgresql://user:password@ep-something.neon.tech/neondb?sslmode=require"`
   Then save. The app restarts.
4. **First load.** The app fills the empty database from `data/throw_log_backup_2026-10-22.xlsx` (21 pitchers, 429 sessions, velo, next-outing dates) and the workbook (4 Build-Up plans). From then on, everything entered is saved in Neon and survives restarts.

The sidebar shows where data is being saved. If it says *a file on this computer*, the secret isn't set.

## Run it in VS Code

1. Open this folder in VS Code (**File ▸ Open Folder…**).
2. Open `run.py` and click **▶ Run Python File** (top right).
   The first run installs the packages, then the app opens in your browser at http://localhost:8501.
3. To stop it, click in the VS Code terminal and press **Ctrl+C**.

Without a `DATABASE_URL`, the app saves to `data/throwing.db` on your computer. To work on the same data as the public app, put the same line in `.streamlit/secrets.toml` (see `.streamlit/secrets.toml.example`). Never commit that file.

## Data

- **Sidebar ▸ Import / backup ▸ Prepare Excel backup** downloads everything in one file: roster, throw log, Build-Up settings and day overrides.
- **Restore an Excel backup** loads one back in. Each player's throw log is replaced with the backup's copy, so nothing is duplicated.
- **Import the ACWR Excel workbook** loads Roster velo and every Build-Up tab. Its Throw Log tab is only imported if you tick the box.

## Model

All the throwing-workload constants are in `model.py`, copied from the workbook's Reference tab. The Build-Up engine settings are in `buildup.py`.
Both were checked cell-for-cell against the workbook: every template, every Throw Log row, and every day of all four Build-Up tabs.

Coaching decision-support tool, not a medical instrument.
