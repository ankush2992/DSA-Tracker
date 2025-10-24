from flask import Flask, render_template, request, redirect, url_for, flash, send_file, jsonify
from datetime import datetime, date, timedelta
from statistics import mean
from sqlalchemy import func, text, inspect
import io, csv, os
import pandas as pd

from config import SQLALCHEMY_DATABASE_URI, SECRET_KEY
from models import db, Topic, Problem, Session, ResolveLog, bootstrap_defaults
from importers import import_excel

def ensure_schema():
    inspector = inspect(db.engine)
    if 'problems' not in inspector.get_table_names():
        return
    columns = {col["name"] for col in inspector.get_columns('problems')}
    statements = []
    if 'first_logged_date' not in columns:
        statements.append("ALTER TABLE problems ADD COLUMN first_logged_date DATE")
    if 'first_logged_minutes' not in columns:
        statements.append("ALTER TABLE problems ADD COLUMN first_logged_minutes INTEGER DEFAULT 0")
    if statements:
        with db.engine.begin() as conn:
            for stmt in statements:
                conn.execute(text(stmt))
            conn.execute(text("UPDATE problems SET first_logged_date = COALESCE(first_logged_date, DATE(created_at))"))
            conn.execute(text("UPDATE problems SET first_logged_minutes = COALESCE(first_logged_minutes, 0)"))

app = Flask(__name__)
app.config["SQLALCHEMY_DATABASE_URI"] = SQLALCHEMY_DATABASE_URI
app.config["SECRET_KEY"] = SECRET_KEY
db.init_app(app)

def init_db():
    with app.app_context():
        db.create_all()
        ensure_schema()
        bootstrap_defaults(db)

init_db()

@app.route('/')
def index():
    total_minutes = db.session.query(func.coalesce(func.sum(Session.duration_minutes), 0)).scalar() or 0
    total_questions = db.session.query(func.count(Session.id)).scalar() or 0
    latest_date = db.session.query(func.max(Session.date)).scalar()

    last7 = date.today() - timedelta(days=6)
    per_topic_qs = db.session.query(Topic.name, func.count(Session.id)).join(Session, Session.topic_id==Topic.id, isouter=True)        .filter((Session.date>=last7) | (Session.date.is_(None))).group_by(Topic.id).all()

    topic_minutes = db.session.query(Topic.name, func.coalesce(func.sum(Session.duration_minutes), 0))        .join(Session, Session.topic_id==Topic.id, isouter=True)        .group_by(Topic.id).order_by(func.sum(Session.duration_minutes).desc()).limit(10).all()

    days = [last7 + timedelta(days=i) for i in range(7)]
    day_labels = [d.strftime("%d %b") for d in days]
    day_minutes = []
    for d in days:
        minutes = db.session.query(func.coalesce(func.sum(Session.duration_minutes), 0)).filter(Session.date==d).scalar() or 0
        day_minutes.append(minutes)

    return render_template('index.html',
                           total_minutes=total_minutes,
                           total_questions=total_questions,
                           latest_date=latest_date,
                           per_topic_qs=per_topic_qs,
                           topic_minutes=topic_minutes,
                           day_labels=day_labels,
                           day_minutes=day_minutes)

@app.route('/topics')
def topics_list():
    topics = Topic.query.order_by(Topic.name).all()
    rows = []
    for t in topics:
        qcount = Session.query.filter_by(topic_id=t.id).count()
        mins = db.session.query(func.coalesce(func.sum(Session.duration_minutes), 0)).filter(Session.topic_id==t.id).scalar() or 0
        rows.append((t, qcount, mins))
    return render_template('topics.html', rows=rows)

@app.route('/topics/new', methods=['POST'])
def topics_new():
    name = request.form.get('name','').strip()
    goal_q = int(request.form.get('goal_questions', 0) or 0)
    goal_m = int(request.form.get('goal_minutes', 0) or 0)
    desc = request.form.get('description','').strip()
    if not name:
        flash('Topic name required', 'danger'); return redirect(url_for('topics_list'))
    if Topic.query.filter(Topic.name.ilike(name)).first():
        flash('Topic already exists', 'warning'); return redirect(url_for('topics_list'))
    db.session.add(Topic(name=name, goal_questions=goal_q, goal_minutes=goal_m, description=desc))
    db.session.commit()
    flash('Topic added', 'success')
    return redirect(url_for('topics_list'))

@app.route('/topics/<int:tid>/delete', methods=['POST'])
def topics_delete(tid):
    t = Topic.query.get_or_404(tid)
    db.session.delete(t); db.session.commit()
    flash('Topic deleted', 'success'); return redirect(url_for('topics_list'))

@app.route('/problems')
def problems_list():
    q = Problem.query.order_by(Problem.created_at.desc()).limit(200).all()
    topics = Topic.query.order_by(Topic.name).all()
    resolve_logs = ResolveLog.query.order_by(ResolveLog.planned_date.desc(), ResolveLog.created_at.desc()).limit(200).all()
    resolve_summary = {}
    resolve_history = []
    for p in q:
        logs_sorted = sorted(p.resolve_logs, key=lambda r: ((r.planned_date or date.min), r.created_at))
        logs_desc = list(reversed(logs_sorted))
        resolve_summary[p.id] = {
            "count": len(p.resolve_logs),
            "planned": sum(1 for log in p.resolve_logs if log.outcome == "Planned"),
            "last_outcome": logs_desc[0].outcome if logs_desc else ""
        }
        if not logs_sorted:
            continue
        solved_logs = [log for log in logs_sorted if log.outcome == "Solved"]
        if not solved_logs:
            continue
        attempts = len(logs_sorted)
        solved_minutes = [log.minutes_spent for log in solved_logs if log.minutes_spent is not None]
        first_solved = solved_logs[0]
        latest_solved = solved_logs[-1]
        latest_entry = logs_sorted[-1]
        best_minutes = min(solved_minutes) if solved_minutes else None
        avg_minutes = round(mean(solved_minutes), 1) if solved_minutes else None
        progress_label = None
        progress_class = None
        minutes_path = None
        has_minutes = (
            len(solved_logs) > 1
            and first_solved.minutes_spent is not None
            and latest_solved.minutes_spent is not None
        )
        if not has_minutes:
            progress_label = "Baseline"
            progress_class = "bg-secondary-subtle text-secondary"
            if first_solved.minutes_spent is not None:
                minutes_path = f"{first_solved.minutes_spent} min"
        else:
            delta = first_solved.minutes_spent - latest_solved.minutes_spent
            if delta > 0:
                progress_label = f"↓ {delta} min"
                progress_class = "bg-success-subtle text-success"
            elif delta < 0:
                progress_label = f"↑ {abs(delta)} min"
                progress_class = "bg-danger-subtle text-danger"
            else:
                progress_label = "→ steady"
                progress_class = "bg-secondary-subtle text-secondary"
            minutes_path = f"{first_solved.minutes_spent} → {latest_solved.minutes_spent}"
        resolve_history.append({
            "problem": p,
            "attempts": attempts,
            "solved_count": len(solved_logs),
            "best_minutes": best_minutes,
            "avg_minutes": avg_minutes,
            "latest_minutes": latest_solved.minutes_spent if latest_solved.minutes_spent is not None else None,
            "latest_date": latest_solved.planned_date,
            "latest_outcome": latest_entry.outcome if latest_entry else None,
            "progress_label": progress_label,
            "progress_class": progress_class,
            "minutes_path": minutes_path,
            "first_date": first_solved.planned_date,
        })
    resolve_history.sort(key=lambda item: (item["latest_date"] or date.min, item["problem"].id), reverse=True)
    return render_template(
        'problems.html',
        problems=q,
        topics=topics,
        resolve_logs=resolve_logs,
        resolve_summary=resolve_summary,
        resolve_history=resolve_history,
        today=date.today()
    )

@app.route('/problems/new', methods=['POST'])
def problems_new():
    title = request.form.get('title','').strip()
    if not title:
        flash('Title is required', 'danger'); return redirect(url_for('problems_list'))
    link = request.form.get('link','').strip()
    source = request.form.get('source','LeetCode').strip()
    difficulty = request.form.get('difficulty','').strip()
    tags = request.form.get('tags','').strip()
    notes = request.form.get('notes','').strip()
    topic_id = request.form.get('topic_id')
    topic = Topic.query.get(topic_id) if topic_id else None
    logged_date_str = request.form.get('first_logged_date','').strip()
    try:
        first_logged_date = datetime.strptime(logged_date_str, "%Y-%m-%d").date() if logged_date_str else date.today()
    except ValueError:
        first_logged_date = date.today()
    logged_minutes_raw = request.form.get('first_logged_minutes','').strip()
    try:
        first_logged_minutes = int(logged_minutes_raw) if logged_minutes_raw else 0
    except ValueError:
        first_logged_minutes = 0
    p = Problem(
        title=title,
        link=link,
        source=source,
        difficulty=difficulty,
        tags=tags,
        notes=notes,
        topic=topic,
        first_logged_date=first_logged_date,
        first_logged_minutes=first_logged_minutes
    )
    db.session.add(p); db.session.commit()
    flash('Problem added', 'success'); return redirect(url_for('problems_list'))

@app.route('/problems/<int:pid>/edit', methods=['GET','POST'])
def problems_edit(pid):
    problem = Problem.query.get_or_404(pid)
    topics = Topic.query.order_by(Topic.name).all()
    if request.method == 'POST':
        title = request.form.get('title','').strip()
        if title:
            problem.title = title
        problem.source = request.form.get('source','').strip()
        problem.link = request.form.get('link','').strip()
        problem.difficulty = request.form.get('difficulty','').strip()
        problem.tags = request.form.get('tags','').strip()
        problem.notes = request.form.get('notes','').strip()
        if 'first_logged_date' in request.form:
            logged_date_str = request.form.get('first_logged_date','').strip()
            if logged_date_str:
                try:
                    problem.first_logged_date = datetime.strptime(logged_date_str, "%Y-%m-%d").date()
                except ValueError:
                    pass
            else:
                problem.first_logged_date = None
        if 'first_logged_minutes' in request.form:
            minutes_raw = request.form.get('first_logged_minutes','').strip()
            if minutes_raw:
                try:
                    problem.first_logged_minutes = int(minutes_raw)
                except ValueError:
                    pass
            else:
                problem.first_logged_minutes = 0
        topic_id = request.form.get('topic_id')
        problem.topic = Topic.query.get(topic_id) if topic_id else None
        db.session.commit()
        flash('Problem updated', 'success'); return redirect(url_for('problems_list'))
    return render_template('problem_edit.html', problem=problem, topics=topics)

@app.route('/problems/resolve', methods=['POST'])
def problems_resolve():
    problem_id = request.form.get('problem_id')
    if not problem_id:
        flash('Select a problem to track a resolve attempt', 'danger'); return redirect(url_for('problems_list'))
    problem = Problem.query.get(problem_id)
    if not problem:
        flash('Problem not found', 'danger'); return redirect(url_for('problems_list'))
    date_str = request.form.get('planned_date')
    try:
        planned_date = datetime.strptime(date_str, "%Y-%m-%d").date() if date_str else date.today()
    except ValueError:
        planned_date = date.today()
    minutes_raw = request.form.get('minutes_spent', '').strip()
    try:
        minutes_spent = int(minutes_raw) if minutes_raw else 0
    except ValueError:
        minutes_spent = 0
    outcome = request.form.get('outcome', 'Planned').strip() or 'Planned'
    if outcome not in ('Planned', 'Solved', 'Not Solved'):
        outcome = 'Planned'
    notes = request.form.get('notes','').strip()
    log = ResolveLog(problem=problem, planned_date=planned_date, minutes_spent=minutes_spent, outcome=outcome, notes=notes)
    db.session.add(log); db.session.commit()
    flash('Resolve entry saved', 'success'); return redirect(url_for('problems_list'))

@app.route('/resolves/<int:rid>/outcome', methods=['POST'])
def resolve_update_outcome(rid):
    log = ResolveLog.query.get_or_404(rid)
    outcome = request.form.get('outcome','').strip()
    if outcome not in ('Planned', 'Solved', 'Not Solved'):
        flash('Invalid outcome', 'danger'); return redirect(url_for('problems_list'))
    minutes_raw = request.form.get('minutes_spent','').strip()
    if minutes_raw:
        try:
            log.minutes_spent = int(minutes_raw)
        except ValueError:
            pass
    log.outcome = outcome
    db.session.commit()
    flash('Resolve outcome updated', 'success'); return redirect(url_for('problems_list'))

@app.route('/sessions')
def sessions_list():
    sessions = Session.query.order_by(Session.date.desc(), Session.id.desc()).limit(200).all()
    topics = Topic.query.order_by(Topic.name).all()
    problems = Problem.query.order_by(Problem.created_at.desc()).limit(200).all()
    return render_template('sessions.html', sessions=sessions, topics=topics, problems=problems)

@app.route('/sessions/new', methods=['POST'])
def sessions_new():
    problem_id = request.form.get('problem_id')
    topic_id = request.form.get('topic_id')
    minutes = int(request.form.get('duration_minutes', 0) or 0)
    date_str = request.form.get('date')
    outcome = request.form.get('outcome','Solved')
    notes = request.form.get('notes','').strip()
    d = date.today()
    if date_str:
        try:
            d = datetime.strptime(date_str, "%Y-%m-%d").date()
        except:
            pass
    s = Session(
        date=d,
        duration_minutes=minutes,
        outcome=outcome,
        topic_id=int(topic_id) if topic_id else None,
        problem_id=int(problem_id) if problem_id else None,
        approach_notes=notes
    )
    db.session.add(s); db.session.commit()
    flash('Session logged', 'success'); return redirect(url_for('sessions_list'))

@app.route('/sessions/bulk', methods=['POST'])
def sessions_bulk():
    """
    Accepts multiple lines, each like:
    YYYY-MM-DD | Topic | Title | Minutes | Outcome | Notes
    Title can be empty if not tied to a specific problem.
    """
    text = request.form.get('bulk','').strip()
    if not text:
        flash('No data provided', 'warning'); return redirect(url_for('sessions_list'))
    imported = 0
    for line in text.splitlines():
        parts = [p.strip() for p in line.split('|')]
        if len(parts)<4: 
            continue
        d = parts[0] or date.today().isoformat()
        try:
            d_parsed = datetime.strptime(d, "%Y-%m-%d").date()
        except:
            d_parsed = date.today()
        topic_name = parts[1] or None
        title = parts[2] or ""
        minutes = int(parts[3]) if len(parts)>3 and parts[3].isdigit() else 0
        outcome = parts[4] if len(parts)>4 else "Solved"
        notes = parts[5] if len(parts)>5 else ""
        topic = None
        if topic_name:
            topic = Topic.query.filter(Topic.name.ilike(topic_name)).first()
            if not topic:
                topic = Topic(name=topic_name); db.session.add(topic); db.session.flush()
        problem = None
        if title:
            problem = Problem.query.filter(Problem.title.ilike(title)).first()
            if not problem:
                problem = Problem(title=title, topic=topic); db.session.add(problem); db.session.flush()
        s = Session(date=d_parsed, duration_minutes=minutes, outcome=outcome, topic=topic or (problem.topic if problem else None), problem=problem, approach_notes=notes)
        db.session.add(s)
        imported += 1
    db.session.commit()
    flash(f'Imported {imported} sessions', 'success'); return redirect(url_for('sessions_list'))

@app.route('/import', methods=['GET','POST'])
def import_view():
    if request.method == 'POST':
        f = request.files.get('excel')
        if not f:
            flash('Upload an Excel workbook', 'danger'); return redirect(url_for('import_view'))
        path = os.path.join(app.instance_path, 'uploads')
        os.makedirs(path, exist_ok=True)
        save_path = os.path.join(path, f.filename)
        f.save(save_path)
        rows = import_excel(save_path)
        flash(f'Imported rows from Excel: {rows}', 'success')
        return redirect(url_for('index'))
    return render_template('import.html')

@app.route('/export/csv')
def export_csv():
    si = io.StringIO()
    cw = csv.writer(si)
    cw.writerow(["date","topic","problem","minutes","outcome","source","difficulty","link","tags","notes"])
    q = db.session.query(Session, Problem, Topic).join(Problem, Session.problem_id==Problem.id, isouter=True).join(Topic, Session.topic_id==Topic.id, isouter=True).all()
    for s, p, t in q:
        cw.writerow([
            s.date.isoformat() if s.date else "",
            t.name if t else "",
            p.title if p else "",
            s.duration_minutes,
            s.outcome,
            p.source if p else "",
            p.difficulty if p else "",
            p.link if p else "",
            p.tags if p else "",
            s.approach_notes or (p.notes if p else "")
        ])
    output = io.BytesIO()
    output.write(si.getvalue().encode())
    output.seek(0)
    return send_file(output, mimetype='text/csv', as_attachment=True, download_name='dsa_progress_export.csv')

@app.route('/api/stats')
def api_stats():
    last30 = date.today() - timedelta(days=29)
    days = [last30 + timedelta(days=i) for i in range(30)]
    data = []
    for d in days:
        minutes = db.session.query(func.coalesce(func.sum(Session.duration_minutes), 0)).filter(Session.date==d).scalar() or 0
        data.append({"date": d.isoformat(), "minutes": minutes})
    return jsonify({"series": data})

if __name__ == '__main__':
    app.run(debug=True)
