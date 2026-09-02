"""PostgreSQL 连接与建表。"""
import os
import time

import psycopg
from psycopg.rows import dict_row

from .auth import hash_password
from .seed_data import SEED_POINTS

DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql://ccyuwen:ccyuwen@127.0.0.1:5432/ccyuwen",
)

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS users (
    id SERIAL PRIMARY KEY,
    name TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    role TEXT NOT NULL CHECK (role IN ('admin', 'user'))
);

CREATE TABLE IF NOT EXISTS resources (
    id SERIAL PRIMARY KEY,
    owner_type TEXT NOT NULL CHECK (owner_type IN ('official', 'user')),
    owner_id INTEGER REFERENCES users(id),
    path TEXT NOT NULL,
    filename TEXT NOT NULL,
    mime TEXT,
    status TEXT NOT NULL DEFAULT 'stored' CHECK (status IN ('stored', 'extracted')),
    uploaded_by INTEGER REFERENCES users(id),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS knowledge_draft (
    id SERIAL PRIMARY KEY,
    kind TEXT NOT NULL,
    level TEXT NOT NULL,
    prompt TEXT NOT NULL,
    answer TEXT NOT NULL,
    tags TEXT NOT NULL DEFAULT '',
    source TEXT NOT NULL DEFAULT '',
    source_resource_id INTEGER REFERENCES resources(id),
    created_by INTEGER REFERENCES users(id),
    status TEXT NOT NULL DEFAULT 'draft' CHECK (status IN ('draft', 'discarded', 'published')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS knowledge_published (
    id SERIAL PRIMARY KEY,
    kind TEXT NOT NULL,
    level TEXT NOT NULL,
    prompt TEXT NOT NULL,
    answer TEXT NOT NULL,
    tags TEXT NOT NULL DEFAULT '',
    source TEXT NOT NULL DEFAULT '',
    source_resource_id INTEGER,
    draft_id INTEGER,
    embedding BYTEA,
    published_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS courses (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id),
    name TEXT NOT NULL,
    note TEXT NOT NULL DEFAULT '',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS course_items (
    course_id INTEGER NOT NULL REFERENCES courses(id) ON DELETE CASCADE,
    point_id INTEGER NOT NULL REFERENCES knowledge_published(id),
    sort INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (course_id, point_id)
);

CREATE TABLE IF NOT EXISTS review_state (
    user_id INTEGER NOT NULL,
    course_id INTEGER NOT NULL,
    point_id INTEGER NOT NULL,
    n INTEGER NOT NULL DEFAULT 0,
    ef REAL NOT NULL DEFAULT 2.5,
    interval INTEGER NOT NULL DEFAULT 0,
    due DATE,
    lapses INTEGER NOT NULL DEFAULT 0,
    last DATE,
    PRIMARY KEY (user_id, course_id, point_id)
);

CREATE TABLE IF NOT EXISTS review_log (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL,
    course_id INTEGER NOT NULL,
    point_id INTEGER NOT NULL,
    quality INTEGER NOT NULL,
    is_new BOOLEAN NOT NULL,
    correct BOOLEAN NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
"""


def connect():
    conn = psycopg.connect(DATABASE_URL, row_factory=dict_row)
    conn.execute("SET client_encoding TO 'UTF8'")
    return conn


def wait_connect(retries=30):
    last = None
    for _ in range(retries):
        try:
            conn = connect()
            conn.close()
            return
        except Exception as exc:
            last = exc
            time.sleep(1)
    raise last


def init_db():
    wait_connect()
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute(SCHEMA_SQL)
            _ensure_user(cur, "admin", "admin123", "admin")
            _ensure_user(cur, "kid", "kid123", "user")
            _seed_published(cur)
            _seed_default_courses(cur)
        conn.commit()


def _ensure_user(cur, name, password, role):
    cur.execute("SELECT id FROM users WHERE name = %s", (name,))
    if cur.fetchone():
        return
    cur.execute(
        "INSERT INTO users (name, password_hash, role) VALUES (%s, %s, %s)",
        (name, hash_password(password), role),
    )


def _seed_published(cur):
    cur.execute("SELECT COUNT(*) AS n FROM knowledge_published")
    if cur.fetchone()["n"] > 0:
        return
    for point in SEED_POINTS:
        cur.execute(
            """
            INSERT INTO knowledge_published (kind, level, prompt, answer, tags, source)
            VALUES (%s, %s, %s, %s, %s, %s)
            """,
            (point["kind"], point["level"], point["prompt"], point["answer"], point["tags"], point["source"]),
        )


def _seed_default_courses(cur):
    cur.execute("UPDATE courses SET name = %s WHERE name ~ %s", ("默认课程", r"^\?+$"))
    cur.execute("SELECT id FROM knowledge_published ORDER BY kind, level, id")
    points = cur.fetchall()
    if not points:
        return
    cur.execute("SELECT id FROM users WHERE role = 'user'")
    for user in cur.fetchall():
        cur.execute("SELECT id FROM courses WHERE user_id = %s", (user["id"],))
        if cur.fetchone():
            continue
        cur.execute(
            "INSERT INTO courses (user_id, name, note) VALUES (%s, %s, %s) RETURNING id",
            (user["id"], "默认课程", "系统预置，含已发布知识点"),
        )
        course_id = cur.fetchone()["id"]
        for index, point in enumerate(points):
            cur.execute(
                "INSERT INTO course_items (course_id, point_id, sort) VALUES (%s, %s, %s)",
                (course_id, point["id"], index),
            )
