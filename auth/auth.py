# auth/auth.py
import os
import json
import bcrypt
from typing import Dict

# path to the JSON file storing user -> hashed password (utf-8 string)
USERS_PATH = os.path.join(os.getcwd(), "auth", "authorized_users.json")


def _ensure_auth_file():
    dirpath = os.path.dirname(USERS_PATH)
    if not os.path.exists(dirpath):
        os.makedirs(dirpath, exist_ok=True)
    if not os.path.exists(USERS_PATH):
        with open(USERS_PATH, "w", encoding="utf-8") as f:
            json.dump({"users": {}}, f, indent=2)


def _load_users() -> Dict[str, str]:
    _ensure_auth_file()
    with open(USERS_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)
    return data.get("users", {})


def _save_users(users: Dict[str, str]):
    _ensure_auth_file()
    with open(USERS_PATH, "w", encoding="utf-8") as f:
        json.dump({"users": users}, f, indent=2)


def add_user(username: str, password: str) -> None:
    """
    Adds or updates a user. Hashes the password with bcrypt.
    """
    if not username:
        raise ValueError("username required")
    if not password:
        raise ValueError("password required")
    users = _load_users()
    hashed = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt())
    users[username] = hashed.decode("utf-8")
    _save_users(users)


def verify_user(username: str, password: str) -> bool:
    """
    Returns True if username exists and provided password matches stored hash.

    Additional convenience feature:
    - If the stored value for a user does NOT look like a bcrypt hash (i.e. doesn't
      start with '$2'), we treat it as a plaintext legacy password. On a successful
      match, we re-hash and replace it with the bcrypt hash (migration).
    """
    if not username or not password:
        return False
    users = _load_users()
    stored = users.get(username)
    if not stored:
        return False

    # Heuristic: bcrypt hashes start with "$2" (e.g. "$2b$12$...")
    if isinstance(stored, str) and stored.startswith("$2"):
        try:
            return bcrypt.checkpw(password.encode("utf-8"), stored.encode("utf-8"))
        except Exception:
            return False

    # --- Legacy plaintext handling (convenience) ---
    # If stored value is not a bcrypt hash, treat it as plaintext and check directly.
    # If match, migrate to bcrypt (overwrite file with new hash).
    try:
        if password == stored:
            # migrate: replace plaintext with bcrypt hash
            hashed = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
            users[username] = hashed
            _save_users(users)
            return True
        return False
    except Exception:
        return False


def list_users():
    return list(_load_users().keys())
