"""Local, opt-in persistent memory for Capri.

Only facts explicitly saved by the user are stored. No conversation transcript,
audio, credentials, or automatic model-generated memories are saved here.
"""
from __future__ import annotations

import difflib
import os
import re
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

MARKER = "CAPRI_LOCAL_MEMORY_V1"

_WORDS = re.compile(r"[^\wа-яё]+", re.IGNORECASE)
_SECRET = re.compile(
    r"(?i)(парол\w*|password|api[ _-]?key|секретн\w* ключ|private[ _-]?key|"
    r"seed phrase|фраз\w* восстановлен\w*|recovery code|код\w* восстановлен\w*)"
)
_STOP_WORDS = {
    "что", "это", "как", "для", "про", "мне", "тебе", "меня", "моя", "мой", "мои",
    "ты", "она", "они", "есть", "был", "была", "будет", "чтобы", "если", "когда",
    "или", "при", "надо", "можно", "нужно", "пожалуйста", "запомни", "сохрани",
}


def normalize(text: str) -> str:
    """Normalize a fact for duplicate detection and search."""
    text = text.casefold().replace("ё", "е")
    return _WORDS.sub(" ", text).strip()


def default_database_path() -> Path:
    """Keep personal memory outside the Git repository and release archives."""
    local_app_data = os.environ.get("LOCALAPPDATA")
    if local_app_data:
        return Path(local_app_data) / "Capri" / "memory.sqlite3"
    app_data = os.environ.get("APPDATA")
    if app_data:
        return Path(app_data) / "Capri" / "memory.sqlite3"
    return Path.home() / ".capri" / "memory.sqlite3"


class MemoryStore:
    """SQLite storage with explicit save, search, delete and clear operations."""

    def __init__(self, path: str | os.PathLike[str] | None = None):
        self.path = Path(path) if path is not None else default_database_path()
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        con = sqlite3.connect(str(self.path), timeout=5)
        con.row_factory = sqlite3.Row
        con.execute("PRAGMA busy_timeout=5000")
        return con

    @contextmanager
    def _session(self):
        """Commit on success and always close the connection."""
        con = self._connect()
        try:
            with con:
                yield con
        finally:
            con.close()

    def _initialize(self) -> None:
        with self._session() as con:
            con.execute(
                """CREATE TABLE IF NOT EXISTS memories (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    content TEXT NOT NULL,
                    normalized TEXT NOT NULL UNIQUE,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )"""
            )
            con.execute("CREATE INDEX IF NOT EXISTS idx_memories_updated ON memories(updated_at)")

    @staticmethod
    def looks_sensitive(content: str) -> bool:
        """A basic guard against storing credential-like material by accident."""
        return bool(_SECRET.search(content or ""))

    def remember(self, content: str) -> tuple[int, bool]:
        """Save a user-approved fact. Return (id, was_created)."""
        content = re.sub(r"\s+", " ", (content or "")).strip(" \t\r\n.,;:")
        if not content:
            raise ValueError("Нельзя сохранить пустой факт.")
        if len(content) > 1000:
            raise ValueError("Один факт должен быть не длиннее 1000 символов.")
        if self.looks_sensitive(content):
            raise ValueError("Похоже на пароль или секретный ключ. Такие данные в память Капри не сохраняются.")
        norm = normalize(content)
        if not norm:
            raise ValueError("Не получилось распознать текст факта.")
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        with self._session() as con:
            row = con.execute("SELECT id FROM memories WHERE normalized=?", (norm,)).fetchone()
            if row:
                con.execute("UPDATE memories SET content=?, updated_at=? WHERE id=?", (content, now, row["id"]))
                return int(row["id"]), False
            cur = con.execute(
                "INSERT INTO memories(content, normalized, created_at, updated_at) VALUES(?,?,?,?)",
                (content, norm, now, now),
            )
            return int(cur.lastrowid), True

    def list_memories(self, limit: int = 20) -> list[dict[str, Any]]:
        limit = max(1, min(int(limit), 100))
        with self._session() as con:
            rows = con.execute(
                "SELECT id, content, created_at, updated_at FROM memories ORDER BY updated_at DESC, id DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [dict(row) for row in rows]

    def count(self) -> int:
        with self._session() as con:
            row = con.execute("SELECT COUNT(*) AS n FROM memories").fetchone()
        return int(row["n"])

    def find(self, query: str, limit: int = 5) -> list[dict[str, Any]]:
        """Find likely matching facts; results include a numeric relevance score."""
        q = normalize(query)
        if not q:
            return []
        query_words = {w for w in q.split() if len(w) >= 2 and w not in _STOP_WORDS}
        all_rows = self.list_memories(limit=100)
        scored: list[dict[str, Any]] = []
        for item in all_rows:
            norm = normalize(item["content"])
            content_words = set(norm.split())
            overlap = len(query_words & content_words) / max(1, len(query_words))
            ratio = difflib.SequenceMatcher(None, q, norm).ratio()
            score = max(overlap, ratio * 0.75)
            if q in norm or norm in q:
                score = max(score, 0.95)
            if score >= 0.25:
                scored.append({**item, "score": score})
        scored.sort(key=lambda x: (x["score"], x["updated_at"], x["id"]), reverse=True)
        return scored[: max(1, min(int(limit), 20))]

    def delete(self, memory_id: int) -> bool:
        with self._session() as con:
            cur = con.execute("DELETE FROM memories WHERE id=?", (int(memory_id),))
            return cur.rowcount > 0

    def clear(self) -> int:
        with self._session() as con:
            cur = con.execute("DELETE FROM memories")
            return int(cur.rowcount)

    def context_for(self, question: str, max_chars: int = 1200) -> str:
        """Return a small local context for Qwen; never sends it to a remote provider."""
        rows = self.find(question, limit=5)
        # Small profile facts, such as the user's preferred name, can help even when a
        # particular question does not share keywords. If nothing matches, use only the
        # three latest user-saved facts rather than the full database.
        if not rows:
            rows = self.list_memories(limit=3)
        pieces: list[str] = []
        used = 0
        for item in rows:
            line = f"- {item['content']}"
            if used + len(line) + 1 > max_chars:
                continue
            pieces.append(line)
            used += len(line) + 1
        return "\n".join(pieces)
