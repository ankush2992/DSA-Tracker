import pandas as pd
from dateutil import parser as dtparser
from models import db, Topic, Problem, Session

COLUMN_ALIASES = {
    "topic": ["topic", "category", "subject"],
    "title": ["title", "problem", "question", "name"],
    "link": ["link", "url"],
    "source": ["source", "platform"],
    "difficulty": ["difficulty", "level"],
    "tags": ["tags", "tag"],
    "minutes": ["minutes", "time", "duration", "time (min)", "mins", "minute"],
    "date": ["date", "day"],
    "outcome": ["outcome", "status", "result"],
    "notes": ["notes", "remarks, comment".replace(",", "")]  # avoid comma in list
}

def normalize_columns(df):
    mapping = {}
    lower_cols = {c.lower().strip(): c for c in df.columns if isinstance(c, str)}
    for key, aliases in COLUMN_ALIASES.items():
        for a in aliases:
            if a in lower_cols:
                mapping[key] = lower_cols[a]
                break
    return mapping

def import_excel(path):
    xls = pd.ExcelFile(path)
    total_rows = 0
    for sheet in xls.sheet_names:
        if not (sheet.lower().startswith("week") or sheet.lower() in {"summary", "other prep"}):
            continue
        df = pd.read_excel(path, sheet_name=sheet)
        if df.empty:
            continue
        mapping = normalize_columns(df)
        df = df.fillna("")
        for _, row in df.iterrows():
            title = str(row.get(mapping.get("title",""), "")).strip()
            if not title:
                continue
            topic_name = str(row.get(mapping.get("topic",""), "")).strip() or None
            link = str(row.get(mapping.get("link",""), "")).strip()
            source = str(row.get(mapping.get("source",""), "")).strip() or "LeetCode"
            diff = str(row.get(mapping.get("difficulty",""), "")).strip()
            tags = str(row.get(mapping.get("tags",""), "")).strip()
            minutes_val = row.get(mapping.get("minutes",""), 0)
            try:
                minutes = int(float(minutes_val)) if str(minutes_val).strip() else 0
            except:
                minutes = 0
            date_raw = str(row.get(mapping.get("date",""), "")).strip()
            outcome = str(row.get(mapping.get("outcome",""), "")).strip() or ("Solved" if minutes>0 else "")
            notes = str(row.get(mapping.get("notes",""), "")).strip()

            topic = None
            if topic_name:
                topic = Topic.query.filter(Topic.name.ilike(topic_name)).first()
                if not topic:
                    topic = Topic(name=topic_name)
                    db.session.add(topic)
                    db.session.flush()
            problem = Problem.query.filter_by(title=title, link=link).first()
            if not problem:
                problem = Problem(title=title, link=link, source=source, difficulty=diff, tags=tags, topic=topic, notes=notes)
                db.session.add(problem)
                db.session.flush()
            if minutes>0 or outcome:
                dt = None
                if date_raw:
                    try:
                        dt = dtparser.parse(date_raw).date()
                    except:
                        dt = None
                sess = Session(
                    date=dt,
                    duration_minutes=minutes,
                    outcome=outcome or "Solved",
                    topic=topic or problem.topic,
                    problem=problem,
                    approach_notes=notes
                )
                db.session.add(sess)
            total_rows += 1
    db.session.commit()
    return total_rows
