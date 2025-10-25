from datetime import datetime, date
from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()

class Topic(db.Model):
    __tablename__ = "topics"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), unique=True, nullable=False)
    goal_questions = db.Column(db.Integer, default=0)
    goal_minutes = db.Column(db.Integer, default=0)
    description = db.Column(db.Text, default="")
    problems = db.relationship("Problem", backref="topic", lazy=True, cascade="all, delete-orphan")
    sessions = db.relationship("Session", backref="topic", lazy=True, cascade="all, delete-orphan")

class Problem(db.Model):
    __tablename__ = "problems"
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(255), nullable=False)
    source = db.Column(db.String(50), default="LeetCode")
    link = db.Column(db.String(512), default="")
    difficulty = db.Column(db.String(20), default="")
    tags = db.Column(db.String(255), default="")
    notes = db.Column(db.Text, default="")
    topic_id = db.Column(db.Integer, db.ForeignKey("topics.id"), nullable=True)
    first_logged_date = db.Column(db.Date, default=date.today)
    first_logged_minutes = db.Column(db.Integer, default=0)
    needs_review = db.Column(db.Boolean, default=False)
    review_priority = db.Column(db.String(20), default="Normal")
    next_review_date = db.Column(db.Date, nullable=True)
    review_notes = db.Column(db.Text, default="")
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    resolve_logs = db.relationship("ResolveLog", backref="problem", lazy=True, cascade="all, delete-orphan")

class Session(db.Model):
    __tablename__ = "sessions"
    id = db.Column(db.Integer, primary_key=True)
    date = db.Column(db.Date, default=datetime.utcnow)
    duration_minutes = db.Column(db.Integer, default=0)
    attempts = db.Column(db.Integer, default=1)
    outcome = db.Column(db.String(50), default="Solved")
    approach_notes = db.Column(db.Text, default="")
    topic_id = db.Column(db.Integer, db.ForeignKey("topics.id"), nullable=True)
    problem_id = db.Column(db.Integer, db.ForeignKey("problems.id"), nullable=True)
    problem = db.relationship("Problem", backref="sessions", lazy=True)

class ResolveLog(db.Model):
    __tablename__ = "resolve_logs"
    id = db.Column(db.Integer, primary_key=True)
    problem_id = db.Column(db.Integer, db.ForeignKey("problems.id"), nullable=False)
    planned_date = db.Column(db.Date, default=date.today, nullable=False)
    minutes_spent = db.Column(db.Integer, default=0)
    outcome = db.Column(db.String(20), default="Planned")
    notes = db.Column(db.Text, default="")
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

def bootstrap_defaults(db):
    if Topic.query.count() == 0:
        default_topics = [
            "Arrays", "Strings", "Two Pointers", "Sliding Window", "Hashing",
            "Stack", "Queue", "Linked List", "Binary Tree", "BST",
            "Heap / Priority Queue", "Graphs", "DFS/BFS", "Greedy",
            "Dynamic Programming", "Backtracking", "Bit Manipulation",
            "Math", "Binary Search", "Misc"
        ]
        for t in default_topics:
            db.session.add(Topic(name=t))
        db.session.commit()
