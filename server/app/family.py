"""家长账号、家庭关联、作用学生解析。"""
import secrets

from fastapi import HTTPException

LINK_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
STUDENT_ROLE = "user"
PARENT_ROLE = "parent"
ADMIN_ROLE = "admin"
DEMO_PARENT_NAME = "parent"
DEMO_STUDENT_NAME = "kid"
DEMO_LINK_CODE = "KID123"


def generate_link_code():
    return "".join(secrets.choice(LINK_ALPHABET) for _ in range(6))


def is_parent(user):
    return (user or {}).get("role") == PARENT_ROLE


def is_student(user):
    return (user or {}).get("role") == STUDENT_ROLE


def is_admin(user):
    return (user or {}).get("role") == ADMIN_ROLE


def require_parent(user):
    if not is_parent(user):
        raise HTTPException(status_code=403, detail="需要家长账号")
    return user


def require_student(user):
    if not is_student(user):
        raise HTTPException(status_code=403, detail="请用孩子的账号练习")
    return user


def linked_student_ids(conn, parent_id):
    rows = conn.execute(
        "SELECT student_id FROM family_links WHERE parent_id = %s ORDER BY student_id",
        (parent_id,),
    ).fetchall()
    return [int(row["student_id"]) for row in rows]


def is_linked(conn, parent_id, student_id):
    row = conn.execute(
        "SELECT 1 FROM family_links WHERE parent_id = %s AND student_id = %s",
        (parent_id, student_id),
    ).fetchone()
    return bool(row)


def acting_student_id(user, student_id=None):
    """家长必须指定已关联的孩子；学生只能看自己。"""
    if is_student(user):
        if student_id not in (None, "", 0, "0"):
            try:
                asked = int(student_id)
            except (TypeError, ValueError):
                raise HTTPException(status_code=400, detail="孩子账号无效")
            if asked != int(user["id"]):
                raise HTTPException(status_code=403, detail="只能查看自己的学习")
        return int(user["id"])
    if is_parent(user):
        if student_id in (None, "", 0, "0"):
            raise HTTPException(status_code=400, detail="请选择孩子")
        try:
            return int(student_id)
        except (TypeError, ValueError):
            raise HTTPException(status_code=400, detail="孩子账号无效")
    raise HTTPException(status_code=403, detail="没有权限查看孩子的学习")


def ensure_parent_can_view(conn, user, student_id):
    if is_student(user) and int(user["id"]) == int(student_id):
        return
    if is_parent(user) and is_linked(conn, user["id"], student_id):
        return
    raise HTTPException(status_code=403, detail="未关联该学生")


def serialize_public_user(row, include_link_code=False):
    data = {"id": row["id"], "name": row["name"], "role": row["role"]}
    if include_link_code:
        data["linkCode"] = row.get("link_code") or ""
    return data


def find_student_by_name(conn, name):
    return conn.execute(
        "SELECT * FROM users WHERE name = %s AND role = %s",
        (str(name or "").strip(), STUDENT_ROLE),
    ).fetchone()


def list_linked_students(conn, parent_id):
    return conn.execute(
        """
        SELECT u.id, u.name, u.role, u.link_code
        FROM family_links f
        JOIN users u ON u.id = f.student_id
        WHERE f.parent_id = %s
        ORDER BY u.id
        """,
        (parent_id,),
    ).fetchall()


def load_student(conn, student_id):
    return conn.execute(
        "SELECT id, name, role, link_code FROM users WHERE id = %s AND role = %s",
        (student_id, STUDENT_ROLE),
    ).fetchone()


def parse_minutes_cap(value, default=0):
    if value is None:
        return default
    try:
        number = int(value)
    except (TypeError, ValueError):
        return default
    return min(max(number, 0), 180)


def link_parent_to_student(conn, parent_id, student_name, link_code):
    student = find_student_by_name(conn, student_name)
    if not student:
        raise HTTPException(status_code=404, detail="没有这个孩子账号")
    expected = str(student.get("link_code") or "").strip().upper()
    given = str(link_code or "").strip().upper()
    if not expected or expected != given:
        raise HTTPException(status_code=400, detail="家庭码不对")
    if is_linked(conn, parent_id, student["id"]):
        return student
    conn.execute(
        "INSERT INTO family_links (parent_id, student_id) VALUES (%s, %s)",
        (parent_id, student["id"]),
    )
    return student
