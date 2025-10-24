# DSA Tracker — Local Web App

A robust local website to track your DSA progress: topics, problems, time per session, outcomes, and quick bulk imports.
Built with Flask + SQLite so you can run it offline on `localhost` and freely add multiple questions and timings.

## Features
- Dashboard with last-7-days minutes and top topics
- Topics CRUD with optional goals (questions/minutes)
- Problems: add singly or **bulk add** multiple lines (auto-creates sessions when minutes provided)
- Sessions: quick log form and **bulk log** parser
- Excel Importer: reads sheets named `Week 1`, `Week 2`, ... (and `Summary`, `Other Prep`), mapping common columns:
  - Topic, Problem/Title, Link, Source, Difficulty, Tags, Minutes/Time, Date, Outcome, Notes
- CSV Export of all sessions
- SQLite DB by default (`dsa_tracker.db`)

## Quick Start
```bash
# (optional) create a virtual env
python -m venv .venv
source .venv/bin/activate  # on Windows: .venv\Scripts\activate

pip install -r requirements.txt
python app.py
# open http://127.0.0.1:5000 in your browser
```

## Bulk Formats

### Problems bulk (one per line)
```
Title | Topic | Minutes | Difficulty | Link | Source | Tags | Notes
Two Sum | Arrays | 25 | Easy | https://leetcode.com/problems/two-sum | LeetCode | hashing | used hashmap
```

### Sessions bulk (one per line)
```
YYYY-MM-DD | Topic | Title | Minutes | Outcome | Notes
2025-10-24 | Arrays | Two Sum | 25 | Solved | revised approach
```

## Import from Excel
Go to **Import** in the navbar and upload your workbook (like `DSA_30Day_Tracker.xlsx`). The importer attempts to auto-map logical columns. Unknown columns are ignored.

## Config
- Set `DSA_TRACKER_DB` to change DB path, `DSA_TRACKER_SECRET` to override secret.
```bash
export DSA_TRACKER_DB=sqlite:///C:/path/to/dsa.db
export DSA_TRACKER_SECRET="your-secret"
```

## Notes
- First run seeds common DSA topics.
- All pages cap lists to recent 200 items for speed; data remains in DB.
