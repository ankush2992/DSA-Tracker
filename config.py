import os
BASE_DIR = os.path.abspath(os.path.dirname(__file__))
SQLALCHEMY_DATABASE_URI = os.environ.get('DSA_TRACKER_DB', f"sqlite:///{os.path.join(BASE_DIR, 'dsa_tracker.db')}")
SQLALCHEMY_TRACK_MODIFICATIONS = False
SECRET_KEY = os.environ.get('DSA_TRACKER_SECRET', 'dev-secret-key')
