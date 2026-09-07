"""口令哈希与 JWT。"""
import hashlib
import os
import secrets
from datetime import datetime, timedelta, timezone

import jwt
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from .family import is_admin, is_parent

JWT_SECRET = os.environ.get("JWT_SECRET", "ccyuwen-dev")
JWT_ALG = "HS256"
bearer = HTTPBearer(auto_error=False)


def demo_hints_enabled():
    """Show local demo-account copy only when explicitly enabled or using the dev JWT."""
    raw = os.environ.get("DEMO_HINTS")
    if raw is not None and str(raw).strip() != "":
        return str(raw).strip().lower() in ("1", "true", "yes", "on")
    return os.environ.get("JWT_SECRET", "ccyuwen-dev") == "ccyuwen-dev"


def hash_password(plain):
    salt = secrets.token_hex(8)
    digest = hashlib.pbkdf2_hmac("sha256", plain.encode("utf-8"), salt.encode("utf-8"), 120000)
    return salt + "$" + digest.hex()


def verify_password(plain, stored):
    if not stored or "$" not in stored:
        return False
    salt, digest = stored.split("$", 1)
    check = hashlib.pbkdf2_hmac("sha256", plain.encode("utf-8"), salt.encode("utf-8"), 120000).hex()
    return secrets.compare_digest(check, digest)


def make_token(user):
    payload = {
        "sub": str(user["id"]),
        "name": user["name"],
        "role": user["role"],
        "exp": datetime.now(timezone.utc) + timedelta(days=7),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALG)


def current_user(creds: HTTPAuthorizationCredentials = Depends(bearer)):
    if creds is None:
        raise HTTPException(status_code=401, detail="请先登录")
    try:
        data = jwt.decode(creds.credentials, JWT_SECRET, algorithms=[JWT_ALG])
    except jwt.PyJWTError:
        raise HTTPException(status_code=401, detail="登录已失效")
    return {"id": int(data["sub"]), "name": data.get("name"), "role": data.get("role")}


def require_admin(user=Depends(current_user)):
    if not is_admin(user):
        raise HTTPException(status_code=403, detail="需要管理员")
    return user


def reject_parent_admin(user=Depends(current_user)):
    """家长不能进资源审核 / 原始资料一类接口。"""
    if is_parent(user):
        raise HTTPException(status_code=403, detail="家长不能管理词库")
    return user
