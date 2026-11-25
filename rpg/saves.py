import json
import sqlite3
from pathlib import Path

from .engine import Command, Pack, State, Turn


class Save:
    def __init__(self, path: Path):
        self.connection = sqlite3.connect(path)
        with self.connection:
            self.connection.execute("""
                CREATE TABLE IF NOT EXISTS game (
                    id INTEGER PRIMARY KEY CHECK (id = 1),
                    pack_id TEXT NOT NULL,
                    pack_version INTEGER NOT NULL,
                    location TEXT NOT NULL,
                    flags TEXT NOT NULL,
                    inventory TEXT NOT NULL,
                    turn INTEGER NOT NULL
                )
            """)
            self.connection.execute("""
                CREATE TABLE IF NOT EXISTS events (
                    turn INTEGER PRIMARY KEY,
                    verb TEXT NOT NULL,
                    target TEXT NOT NULL,
                    message TEXT NOT NULL
                )
            """)

    def close(self):
        self.connection.close()

    def load_or_start(self, pack: Pack) -> State:
        with self.connection:
            self.connection.execute(
                "INSERT OR IGNORE INTO game VALUES (1, ?, ?, ?, '[]', '[]', 0)",
                (pack.id, pack.version, pack.start),
            )
            pack_id, version, location, flags, inventory, turn = self.connection.execute(
                "SELECT pack_id, pack_version, location, flags, inventory, turn FROM game"
            ).fetchone()
            if (pack_id, version) != (pack.id, pack.version):
                raise ValueError("Save belongs to a different pack or pack version.")
        return State(location, frozenset(json.loads(flags)), frozenset(json.loads(inventory)), turn)

    def commit(self, previous: State, command: Command, result: Turn) -> None:
        if not result.accepted:
            return
        state = result.state
        with self.connection:
            changed = self.connection.execute(
                "UPDATE game SET location=?, flags=?, inventory=?, turn=? WHERE id=1 AND turn=?",
                (state.location, json.dumps(sorted(state.flags)),
                 json.dumps(sorted(state.inventory)), state.turn, previous.turn),
            ).rowcount
            if changed != 1:
                raise ValueError("Save changed in another session. Reopen it to continue.")
            self.connection.execute(
                "INSERT INTO events VALUES (?, ?, ?, ?)",
                (state.turn, command.verb, command.target, result.message),
            )

    def recent_events(self, through_turn: int, limit: int = 50) -> list[tuple[str, str, str]]:
        rows = self.connection.execute(
            "SELECT verb, target, message FROM events WHERE turn <= ? ORDER BY turn DESC LIMIT ?",
            (through_turn, limit),
        ).fetchall()
        return rows[::-1]
