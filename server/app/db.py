"""PostgreSQL 连接与建表。"""
import os
import time

import psycopg
from psycopg.rows import dict_row

from .auth import hash_password
from .cards import KINDS, LEVELS, decode_filters, encode_filters, fill_group_fields
from .materials import sync_all_official

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
    slug TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'stored' CHECK (status IN ('stored', 'extracted')),
    uploaded_by INTEGER REFERENCES users(id),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS knowledge_draft (
    id SERIAL PRIMARY KEY,
    kind TEXT NOT NULL,
    level TEXT NOT NULL,
    grade TEXT NOT NULL DEFAULT '',
    prompt TEXT NOT NULL,
    answer TEXT NOT NULL,
    tags TEXT NOT NULL DEFAULT '',
    source TEXT NOT NULL DEFAULT '',
    source_resource_id INTEGER REFERENCES resources(id),
    created_by INTEGER REFERENCES users(id),
    point_key TEXT NOT NULL DEFAULT '',
    group_key TEXT NOT NULL DEFAULT '',
    sub_group_key TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'draft' CHECK (status IN ('draft', 'discarded', 'published')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS knowledge_published (
    id SERIAL PRIMARY KEY,
    kind TEXT NOT NULL,
    level TEXT NOT NULL,
    grade TEXT NOT NULL DEFAULT '',
    prompt TEXT NOT NULL,
    answer TEXT NOT NULL,
    tags TEXT NOT NULL DEFAULT '',
    source TEXT NOT NULL DEFAULT '',
    source_resource_id INTEGER,
    draft_id INTEGER,
    point_key TEXT NOT NULL DEFAULT '',
    group_key TEXT NOT NULL DEFAULT '',
    sub_group_key TEXT NOT NULL DEFAULT '',
    embedding BYTEA,
    published_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS courses (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id),
    name TEXT NOT NULL,
    note TEXT NOT NULL DEFAULT '',
    kinds TEXT NOT NULL DEFAULT '',
    levels TEXT NOT NULL DEFAULT '',
    grades TEXT NOT NULL DEFAULT '',
    new_energy INTEGER NOT NULL DEFAULT 30,
    review_energy INTEGER NOT NULL DEFAULT 30,
    review_default_test BOOLEAN NOT NULL DEFAULT FALSE,
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
            _migrate(cur)
            _ensure_user(cur, "admin", "admin123", "admin")
            _ensure_user(cur, "kid", "kid123", "user")
            _seed_official_packs(cur)
            _seed_default_courses(cur)
        conn.commit()


def _migrate(cur):
    cur.execute("ALTER TABLE courses ADD COLUMN IF NOT EXISTS kinds TEXT NOT NULL DEFAULT ''")
    cur.execute("ALTER TABLE courses ADD COLUMN IF NOT EXISTS levels TEXT NOT NULL DEFAULT ''")
    cur.execute("ALTER TABLE courses ADD COLUMN IF NOT EXISTS grades TEXT NOT NULL DEFAULT ''")
    cur.execute("ALTER TABLE courses ADD COLUMN IF NOT EXISTS new_energy INTEGER NOT NULL DEFAULT 30")
    cur.execute("ALTER TABLE courses ADD COLUMN IF NOT EXISTS review_energy INTEGER NOT NULL DEFAULT 30")
    cur.execute("ALTER TABLE courses ADD COLUMN IF NOT EXISTS review_default_test BOOLEAN NOT NULL DEFAULT FALSE")
    cur.execute("ALTER TABLE knowledge_draft ADD COLUMN IF NOT EXISTS grade TEXT NOT NULL DEFAULT ''")
    cur.execute("ALTER TABLE knowledge_published ADD COLUMN IF NOT EXISTS grade TEXT NOT NULL DEFAULT ''")
    cur.execute("ALTER TABLE knowledge_draft ADD COLUMN IF NOT EXISTS point_key TEXT NOT NULL DEFAULT ''")
    cur.execute("ALTER TABLE knowledge_published ADD COLUMN IF NOT EXISTS point_key TEXT NOT NULL DEFAULT ''")
    cur.execute("ALTER TABLE knowledge_draft ADD COLUMN IF NOT EXISTS group_key TEXT NOT NULL DEFAULT ''")
    cur.execute("ALTER TABLE knowledge_published ADD COLUMN IF NOT EXISTS group_key TEXT NOT NULL DEFAULT ''")
    cur.execute("ALTER TABLE knowledge_draft ADD COLUMN IF NOT EXISTS sub_group_key TEXT NOT NULL DEFAULT ''")
    cur.execute("ALTER TABLE knowledge_published ADD COLUMN IF NOT EXISTS sub_group_key TEXT NOT NULL DEFAULT ''")
    cur.execute("ALTER TABLE resources ADD COLUMN IF NOT EXISTS slug TEXT NOT NULL DEFAULT ''")
    cur.execute("ALTER TABLE resources ADD COLUMN IF NOT EXISTS synced_version INTEGER NOT NULL DEFAULT 0")
    cur.execute("ALTER TABLE resources ADD COLUMN IF NOT EXISTS synced_hash TEXT NOT NULL DEFAULT ''")
    cur.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS knowledge_published_point_key_uidx
        ON knowledge_published (point_key)
        WHERE point_key <> ''
        """
    )
    cur.execute(
        """
        CREATE INDEX IF NOT EXISTS knowledge_published_group_key_idx
        ON knowledge_published (group_key)
        """
    )
    cur.execute(
        """
        UPDATE courses
        SET kinds = %s, levels = %s
        WHERE name = %s AND (kinds = '' OR kinds IS NULL)
        """,
        (encode_filters(KINDS, KINDS), encode_filters(LEVELS, LEVELS), "默认课程"),
    )
    cur.execute(
        "UPDATE courses SET kinds = %s WHERE name = %s",
        (encode_filters(KINDS, KINDS), "默认课程"),
    )
    cur.execute(
        """
        UPDATE knowledge_published
        SET kind = 'wenyan'
        WHERE kind = 'poem' AND tags LIKE '文言文%'
        """
    )
    cur.execute("SELECT id, kinds FROM courses WHERE name <> %s", ("默认课程",))
    for row in cur.fetchall():
        current = decode_filters(row["kinds"], KINDS)
        if "poem" in current and "wenyan" not in current:
            idx = current.index("poem")
            current.insert(idx + 1, "wenyan")
            cur.execute(
                "UPDATE courses SET kinds = %s WHERE id = %s",
                (encode_filters(current, KINDS), row["id"]),
            )
    _backfill_group_keys(cur)


def _backfill_group_keys(cur):
    cur.execute(
        """
        SELECT id, kind, level, grade, prompt, answer, tags, source, point_key, group_key, sub_group_key
        FROM knowledge_published
        """
    )
    for row in cur.fetchall():
        filled = fill_group_fields(
            {
                "key": row.get("point_key") or "",
                "kind": row["kind"],
                "level": row["level"],
                "grade": row.get("grade") or "",
                "prompt": row["prompt"],
                "answer": row["answer"],
                "tags": row.get("tags") or "",
                "source": row.get("source") or "",
            }
        )
        if (row.get("group_key") or "") != filled["group_key"] or (row.get("sub_group_key") or "") != filled[
            "sub_group_key"
        ]:
            cur.execute(
                "UPDATE knowledge_published SET group_key = %s, sub_group_key = %s WHERE id = %s",
                (filled["group_key"], filled["sub_group_key"], row["id"]),
            )


def _ensure_user(cur, name, password, role):
    cur.execute("SELECT id FROM users WHERE name = %s", (name,))
    if cur.fetchone():
        return
    cur.execute(
        "INSERT INTO users (name, password_hash, role) VALUES (%s, %s, %s)",
        (name, hash_password(password), role),
    )


def _seed_official_packs(cur):
    sync_all_official(cur, force=False)


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
            """
            INSERT INTO courses (user_id, name, note, kinds, levels, grades)
            VALUES (%s, %s, %s, %s, %s, %s)
            RETURNING id
            """,
            (
                user["id"],
                "默认课程",
                "系统预置，含已发布知识点",
                encode_filters(KINDS, KINDS),
                encode_filters(LEVELS, LEVELS),
                "",
            ),
        )
        course_id = cur.fetchone()["id"]
        for index, point in enumerate(points):
            cur.execute(
                "INSERT INTO course_items (course_id, point_id, sort) VALUES (%s, %s, %s)",
                (course_id, point["id"], index),
            )
