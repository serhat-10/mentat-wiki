"""Local full-text search (SQLite FTS5). Returns titles and summaries, not page bodies."""
import re
import sqlite3

from . import util
from .vault import Vault

_COLS = "path UNINDEXED, type UNINDEXED, domain UNINDEXED, value UNINDEXED, effort UNINDEXED, " \
        "idea_status UNINDEXED, title, summary, body"


def _db(v: Vault) -> sqlite3.Connection:
    v.state.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(v.state / "index.db")
    db.execute(f"CREATE VIRTUAL TABLE IF NOT EXISTS pages USING fts5({_COLS})")
    db.execute("CREATE TABLE IF NOT EXISTS seen(path TEXT PRIMARY KEY, sig TEXT)")
    return db


def _db_readonly(v: Vault):
    """Open the existing index read-only (no mkdir, no DDL, no sync). None if it is missing or unusable."""
    path = v.state / "index.db"
    if not path.is_file():
        return None
    try:
        db = sqlite3.connect(f"{path.as_uri()}?mode=ro", uri=True, timeout=0.2)
        db.execute("SELECT 1 FROM pages LIMIT 1")
        return db
    except sqlite3.Error:
        return None


def _title(body: str, fallback: str) -> str:
    m = re.search(r"^#\s+(.+)$", body, re.M)
    return m.group(1).strip() if m else fallback


def sync(v: Vault) -> None:
    db = _db(v)
    seen = dict(db.execute("SELECT path, sig FROM seen"))
    current = set()
    for p in v.pages():
        rel = p.relative_to(v.root).as_posix()
        current.add(rel)
        st = p.stat()
        sig = f"{st.st_mtime_ns}:{st.st_size}"
        if seen.get(rel) == sig:
            continue
        meta, body = util.parse_frontmatter(p.read_text(encoding="utf-8-sig", errors="replace"))
        db.execute("DELETE FROM pages WHERE path = ?", (rel,))
        db.execute("INSERT INTO pages VALUES (?,?,?,?,?,?,?,?,?)", (
            rel, meta.get("type", ""), meta.get("domain", ""), meta.get("value", ""),
            meta.get("effort", ""), meta.get("idea_status", ""), _title(body, p.stem),
            meta.get("summary", ""), body))
        db.execute("INSERT OR REPLACE INTO seen VALUES (?,?)", (rel, sig))
    for rel in set(seen) - current:
        db.execute("DELETE FROM pages WHERE path = ?", (rel,))
        db.execute("DELETE FROM seen WHERE path = ?", (rel,))
    db.commit()
    db.close()


_sync = sync  # find() has a `sync` parameter that shadows the function


def _fts_query(q: str) -> str:
    terms = re.findall(r"[^\W_]+", q.lower())
    return " OR ".join(f'"{t}"*' for t in terms)


def find(v: Vault, query: str = "", type_: str = None, limit: int = 5, sync: bool = True) -> list:
    """Rows: (path, type, domain, title, summary). Ranked; title and summary weigh most.
    sync=False is read-only: it never writes the index and returns [] when no index exists."""
    if sync:
        _sync(v)
        db = _db(v)
    else:
        db = _db_readonly(v)
        if db is None:
            return []
    where, args = [], []
    if type_:
        where.append("type = ?")
        args.append(type_)
    fq = _fts_query(query)
    if query.strip() and not fq:
        db.close()
        return []  # the query had no searchable words: no results, not arbitrary pages
    if fq:
        sql = ("SELECT path, type, domain, title, summary FROM pages WHERE pages MATCH ? "
               + ("AND " + " AND ".join(where) if where else "")
               + " ORDER BY bm25(pages, 1,1,1,1,1,1, 8, 5, 1) LIMIT ?")
        rows = db.execute(sql, [fq, *args, limit]).fetchall()
    else:
        sql = ("SELECT path, type, domain, title, summary FROM pages"
               + (" WHERE " + " AND ".join(where) if where else "") + " LIMIT ?")
        rows = db.execute(sql, [*args, limit]).fetchall()
    db.close()
    return rows


def ideas(v: Vault, limit: int = 10, status: str = "parked") -> list:
    """Ideas ranked by value minus effort (best payoff for the time first)."""
    sync(v)
    db = _db(v)
    rows = db.execute(
        "SELECT path, title, summary, value, effort FROM pages WHERE type = 'idea' AND idea_status = ?",
        (status,)).fetchall()
    db.close()

    def score(r):
        try:
            return int(r[3]) - int(r[4]), int(r[3])
        except ValueError:
            return (-99, 0)
    return sorted(rows, key=score, reverse=True)[:limit]
