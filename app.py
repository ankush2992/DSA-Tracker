from flask import Flask, render_template, request, redirect, url_for, flash, jsonify
from datetime import datetime, date, timedelta
from statistics import mean
from collections import defaultdict
from sqlalchemy import func, text, inspect

from config import SQLALCHEMY_DATABASE_URI, SECRET_KEY
from models import db, Topic, Problem, Session, ResolveLog, bootstrap_defaults

def ensure_schema():
    inspector = inspect(db.engine)
    if 'problems' not in inspector.get_table_names():
        return
    columns = {col["name"] for col in inspector.get_columns('problems')}
    statements = []
    post_updates = []
    if 'first_logged_date' not in columns:
        statements.append("ALTER TABLE problems ADD COLUMN first_logged_date DATE")
    if 'first_logged_minutes' not in columns:
        statements.append("ALTER TABLE problems ADD COLUMN first_logged_minutes INTEGER DEFAULT 0")
    if 'needs_review' not in columns:
        statements.append("ALTER TABLE problems ADD COLUMN needs_review BOOLEAN DEFAULT 0")
        post_updates.append("UPDATE problems SET needs_review = COALESCE(needs_review, 0)")
    if 'review_priority' not in columns:
        statements.append("ALTER TABLE problems ADD COLUMN review_priority VARCHAR(20) DEFAULT 'Normal'")
        post_updates.append("UPDATE problems SET review_priority = COALESCE(review_priority, 'Normal')")
    if 'next_review_date' not in columns:
        statements.append("ALTER TABLE problems ADD COLUMN next_review_date DATE")
    if 'review_notes' not in columns:
        statements.append("ALTER TABLE problems ADD COLUMN review_notes TEXT DEFAULT ''")
        post_updates.append("UPDATE problems SET review_notes = COALESCE(review_notes, '')")
    if statements:
        with db.engine.begin() as conn:
            for stmt in statements:
                conn.execute(text(stmt))
            conn.execute(text("UPDATE problems SET first_logged_date = COALESCE(first_logged_date, DATE(created_at))"))
            conn.execute(text("UPDATE problems SET first_logged_minutes = COALESCE(first_logged_minutes, 0)"))
            for stmt in post_updates:
                conn.execute(text(stmt))

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
    problems = Problem.query.order_by(Problem.created_at.desc()).limit(500).all()
    topics = Topic.query.order_by(Topic.name).all()
    resolve_summary = {}
    for p in problems:
        logs_sorted = sorted(p.resolve_logs, key=lambda r: ((r.planned_date or date.min), r.created_at), reverse=True)
        latest_log = logs_sorted[0] if logs_sorted else None
        solved_count = sum(1 for log in logs_sorted if log.outcome == "Solved")
        resolve_summary[p.id] = {
            "count": len(p.resolve_logs),
            "last_outcome": latest_log.outcome if latest_log else "",
            "last_date": latest_log.planned_date if latest_log else None,
            "last_minutes": latest_log.minutes_spent if latest_log else None,
            "solved_count": solved_count,
        }
    grouped_map = defaultdict(list)
    for problem in problems:
        key = problem.topic_id if problem.topic_id else "unassigned"
        grouped_map[key].append(problem)
    grouped_topics = []
    for topic in topics:
        bucket = grouped_map.get(topic.id)
        if bucket:
            bucket.sort(key=lambda x: x.created_at or datetime.utcnow(), reverse=True)
            grouped_topics.append({
                "title": topic.name,
                "topic": topic,
                "count": len(bucket),
                "problems": bucket
            })
    if grouped_map.get("unassigned"):
        bucket = grouped_map["unassigned"]
        bucket.sort(key=lambda x: x.created_at or datetime.utcnow(), reverse=True)
        grouped_topics.append({
            "title": "Misc / No Topic",
            "topic": None,
            "count": len(bucket),
            "problems": bucket
        })
    last7 = date.today() - timedelta(days=7)
    recent_solves = ResolveLog.query.filter(
        ResolveLog.outcome == "Solved",
        ResolveLog.planned_date >= last7
    ).count()
    totals = {
        "total": len(problems),
        "needs_review": sum(1 for p in problems if p.needs_review),
        "recent_solves": recent_solves,
    }
    priorities = ["Low", "Normal", "High", "Critical"]
    review_queue_preview = [p for p in problems if p.needs_review][:5]
    return render_template(
        'problems.html',
        problems=problems,
        topics=topics,
        resolve_summary=resolve_summary,
        priorities=priorities,
        totals=totals,
        review_queue_preview=review_queue_preview,
        grouped_topics=grouped_topics,
        today=date.today()
    )

@app.route('/reviews')
def reviews_board():
    problems = Problem.query.order_by(Problem.created_at.desc()).all()
    resolve_logs = ResolveLog.query.order_by(ResolveLog.planned_date.desc(), ResolveLog.created_at.desc()).limit(400).all()
    resolve_history = []
    resolve_summary = {}
    for p in problems:
        logs_sorted = sorted(p.resolve_logs, key=lambda r: ((r.planned_date or date.min), r.created_at))
        logs_desc = list(reversed(logs_sorted))
        latest_entry = logs_desc[0] if logs_desc else None
        solved_logs = [log for log in logs_sorted if log.outcome == "Solved"]
        resolve_summary[p.id] = {
            "count": len(p.resolve_logs),
            "planned": sum(1 for log in p.resolve_logs if log.outcome == "Planned"),
            "last_outcome": latest_entry.outcome if latest_entry else "",
            "last_date": latest_entry.planned_date if latest_entry else None,
            "last_minutes": latest_entry.minutes_spent if latest_entry else None
        }
        if not solved_logs:
            continue
        attempts = len(logs_sorted)
        solved_minutes = [log.minutes_spent for log in solved_logs if log.minutes_spent is not None]
        first_solved = solved_logs[0]
        latest_solved = solved_logs[-1]
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
    review_queue = [p for p in problems if p.needs_review]
    priorities = ["Low", "Normal", "High", "Critical"]
    focus_id = request.args.get('problem_id', type=int)
    focus_problem = Problem.query.get(focus_id) if focus_id else None
    return render_template(
        'reviews.html',
        problems=problems,
        review_queue=review_queue,
        resolve_logs=resolve_logs,
        resolve_history=resolve_history,
        resolve_summary=resolve_summary,
        priorities=priorities,
        today=date.today(),
        focus_problem=focus_problem
    )

@app.route('/problems/<int:pid>/review', methods=['POST'])
def problems_review(pid):
    problem = Problem.query.get_or_404(pid)
    review_state = request.form.get('review_state')
    if review_state == 'on':
        problem.needs_review = True
    elif review_state == 'off':
        problem.needs_review = False
    elif 'needs_review' in request.form:
        problem.needs_review = request.form.get('needs_review') in ('true', '1', 'on')

    if 'review_priority' in request.form:
        problem.review_priority = request.form.get('review_priority') or 'Normal'
    if 'review_notes' in request.form:
        problem.review_notes = request.form.get('review_notes', '').strip()

    next_review_str = request.form.get('next_review_date')
    if next_review_str is not None:
        if next_review_str:
            try:
                problem.next_review_date = datetime.strptime(next_review_str, "%Y-%m-%d").date()
            except ValueError:
                flash('Invalid next review date', 'warning')
        else:
            problem.next_review_date = None

    db.session.commit()
    flash('Review settings updated', 'success')
    redirect_target = request.form.get('redirect') or request.referrer or url_for('problems_list')
    return redirect(redirect_target)

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
    redirect_target = request.form.get('redirect') or url_for('reviews_board')
    if not problem_id:
        flash('Select a problem to track a resolve attempt', 'danger'); return redirect(redirect_target)
    problem = Problem.query.get(problem_id)
    if not problem:
        flash('Problem not found', 'danger'); return redirect(redirect_target)
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
    flash('Resolve entry saved', 'success'); return redirect(url_for('reviews_board', problem_id=problem.id))

@app.route('/resolves/<int:rid>/outcome', methods=['POST'])
def resolve_update_outcome(rid):
    log = ResolveLog.query.get_or_404(rid)
    outcome = request.form.get('outcome','').strip()
    if outcome not in ('Planned', 'Solved', 'Not Solved'):
        flash('Invalid outcome', 'danger'); return redirect(request.referrer or url_for('reviews_board'))
    minutes_raw = request.form.get('minutes_spent','').strip()
    if minutes_raw:
        try:
            log.minutes_spent = int(minutes_raw)
        except ValueError:
            pass
    log.outcome = outcome
    db.session.commit()
    flash('Resolve outcome updated', 'success'); return redirect(url_for('reviews_board', problem_id=log.problem_id))

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
