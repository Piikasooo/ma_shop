import os

DATABASE = {
    "database": "postgres",
    "user": "postgres",
    "password": "postgres",
    "port": 5432
}

PROJECT_PATH = os.path.dirname(os.path.abspath(__file__))

FIXTURES_PATH = os.path.join(PROJECT_PATH, "fixtures")
