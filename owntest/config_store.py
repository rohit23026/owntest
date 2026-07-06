"""
Configuration store — environments and variables, backed by SQLite (stdlib).

One table holds every setting, keyed by (category, environment, key):
  category     which part of the stack it configures: ui | api | kafka | db
               (kafka/db have no engines yet — the config surface is ready first)
  environment  named value set, e.g. default / staging / prod
  key, value   the variable itself
  description  human note shown in the config page

Intents reference variables as {{category.key}} — e.g. {{api.base_url}} —
in any string field. substitute() resolves them at run time and fails loud
on anything undefined, so a typo can never silently hit the wrong host.

The db lives in the same per-user data dir as intents/reports
(%APPDATA%\\OwnTest or ~/.owntest): survives reinstalls, never in Program Files.
"""
import os
import re
import sqlite3

CATEGORIES = ("ui", "api", "kafka", "db")
_PLACEHOLDER = re.compile(r"\{\{\s*([A-Za-z0-9_.-]+)\s*\}\}")


def data_dir() -> str:
    if os.name == "nt":
        base = os.path.join(os.environ.get("APPDATA", os.path.expanduser("~")), "OwnTest")
    else:
        base = os.path.join(os.path.expanduser("~"), ".owntest")
    os.makedirs(base, exist_ok=True)
    return base


def db_path() -> str:
    return os.path.join(data_dir(), "config.db")


def _connect() -> sqlite3.Connection:
    con = sqlite3.connect(db_path())
    con.execute("CREATE TABLE IF NOT EXISTS environments(name TEXT PRIMARY KEY)")
    con.execute("""CREATE TABLE IF NOT EXISTS config(
        category    TEXT NOT NULL,
        environment TEXT NOT NULL,
        key         TEXT NOT NULL,
        value       TEXT NOT NULL DEFAULT '',
        description TEXT NOT NULL DEFAULT '',
        PRIMARY KEY(category, environment, key))""")
    # a fresh install starts with one environment so the config page isn't empty
    if not con.execute("SELECT 1 FROM environments LIMIT 1").fetchone():
        con.execute("INSERT INTO environments(name) VALUES ('default')")
        con.commit()
    return con


# ---------------- environments ----------------
def list_environments() -> list[str]:
    with _connect() as con:
        return [r[0] for r in con.execute(
            "SELECT name FROM environments ORDER BY name")]


def add_environment(name: str):
    name = name.strip()
    if not re.fullmatch(r"[A-Za-z0-9_-]+", name):
        raise ValueError("environment name must be letters/digits/_/- only")
    with _connect() as con:
        con.execute("INSERT OR IGNORE INTO environments(name) VALUES (?)", (name,))


def delete_environment(name: str):
    with _connect() as con:
        con.execute("DELETE FROM config WHERE environment=?", (name,))
        con.execute("DELETE FROM environments WHERE name=?", (name,))


# ---------------- rows (the table the config page edits) ----------------
def get_rows(category: str, environment: str) -> list[dict]:
    if category not in CATEGORIES:
        raise ValueError(f"unknown category {category!r}; expected one of {CATEGORIES}")
    with _connect() as con:
        return [{"key": k, "value": v, "description": d} for k, v, d in con.execute(
            "SELECT key, value, description FROM config "
            "WHERE category=? AND environment=? ORDER BY key",
            (category, environment))]


def save_rows(category: str, environment: str, rows: list[dict]):
    """Replace the whole (category, environment) slice — matches a table save."""
    if category not in CATEGORIES:
        raise ValueError(f"unknown category {category!r}; expected one of {CATEGORIES}")
    for r in rows:
        if not re.fullmatch(r"[A-Za-z0-9_-]+", r.get("key", "")):
            raise ValueError(f"bad variable name {r.get('key')!r}: letters/digits/_/- only")
    with _connect() as con:
        con.execute("INSERT OR IGNORE INTO environments(name) VALUES (?)", (environment,))
        con.execute("DELETE FROM config WHERE category=? AND environment=?",
                    (category, environment))
        con.executemany(
            "INSERT INTO config(category, environment, key, value, description) "
            "VALUES (?,?,?,?,?)",
            [(category, environment, r["key"], r.get("value", ""),
              r.get("description", "")) for r in rows])


# ---------------- resolution (what the runner calls) ----------------
def variables(environment: str) -> dict[str, str]:
    """All variables of one environment, keyed 'category.key'."""
    with _connect() as con:
        return {f"{c}.{k}": v for c, k, v in con.execute(
            "SELECT category, key, value FROM config WHERE environment=?",
            (environment,))}


def substitute(obj, environment: str | None):
    """
    Deep-replace {{category.key}} placeholders in every string of an intent.
    Fails loud: placeholders with no environment selected, or names the
    environment doesn't define, raise instead of running with a literal.
    """
    found: set[str] = set()

    def scan(o):
        if isinstance(o, str):
            found.update(_PLACEHOLDER.findall(o))
        elif isinstance(o, dict):
            for v in o.values():
                scan(v)
        elif isinstance(o, list):
            for v in o:
                scan(v)

    scan(obj)
    if not found:
        return obj
    if environment is None:
        raise RuntimeError(
            f"intent uses variables {sorted(found)} but no environment was "
            f"selected — pass --env <name> (CLI) or pick one in the app")
    vars_ = variables(environment)
    missing = sorted(found - vars_.keys())
    if missing:
        raise RuntimeError(
            f"undefined variable(s) {missing} in environment {environment!r} — "
            f"define them in the configuration page")

    def walk(o):
        if isinstance(o, str):
            return _PLACEHOLDER.sub(lambda m: vars_[m.group(1)], o)
        if isinstance(o, dict):
            return {k: walk(v) for k, v in o.items()}
        if isinstance(o, list):
            return [walk(v) for v in o]
        return o

    return walk(obj)
