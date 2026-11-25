import json
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Command:
    verb: str
    target: str


@dataclass(frozen=True)
class State:
    location: str
    flags: frozenset[str] = frozenset()
    inventory: frozenset[str] = frozenset()
    turn: int = 0


@dataclass(frozen=True)
class Turn:
    state: State
    message: str
    accepted: bool


@dataclass(frozen=True)
class Rule:
    location: str
    command: Command
    message: str
    requires: frozenset[str]
    needs_items: frozenset[str]
    needs_any_item: frozenset[str]
    sets: frozenset[str]
    gives: frozenset[str]
    consumes: frozenset[str]
    once: str | None
    blocked: str


@dataclass(frozen=True)
class Pack:
    id: str
    version: int
    title: str
    start: str
    goal: str
    locations: dict
    facts: dict
    items: dict
    rules: dict[tuple[str, Command], Rule]
    gates: dict[tuple[str, str], str]
    puzzle_symbols: dict[str, tuple[str, ...]]
    dialogue_style: dict

    @classmethod
    def load(cls, path: Path) -> "Pack":
        data = json.loads(path.read_text(encoding="utf-8"))
        if data["schema"] != 1:
            raise ValueError("Unsupported pack schema")
        locations = data["locations"]
        facts = data["facts"]
        items = data["items"]
        flags = set(data["flags"]) | facts.keys()
        if data["start"] not in locations or data["goal"] not in flags:
            raise ValueError("Invalid start or goal")
        for location in locations.values():
            if set(location["exits"]) - locations.keys():
                raise ValueError("Exit references an unknown location")
        gates = {}
        for gate in data.get("gates", []):
            source, destination = edge = gate["from"], gate["to"]
            flag = gate["requires"]
            if (edge in gates or source not in locations
                    or destination not in locations[source]["exits"] or flag not in flags):
                raise ValueError(f"Invalid or duplicate gate {edge}")
            gates[edge] = flag
        rules = {}
        granted_items = set()
        for entry in data["rules"]:
            rule = Rule(
                location=entry["location"],
                command=Command(entry["verb"], entry["target"]),
                message=entry["message"],
                **{field: frozenset(entry.get(field, [])) for field in
                   ("requires", "needs_items", "needs_any_item", "sets", "gives", "consumes")},
                once=entry.get("once"),
                blocked=entry.get("blocked", "You can't do that yet."),
            )
            key = rule.location, rule.command
            if key in rules or rule.location not in locations or rule.command.verb == "move":
                raise ValueError(f"Invalid or duplicate rule {key}")
            if (rule.requires | rule.sets) - flags:
                raise ValueError(f"Unknown flag in rule {key}")
            if (rule.needs_items | rule.needs_any_item | rule.gives | rule.consumes) - items.keys():
                raise ValueError(f"Unknown item in rule {key}")
            if rule.once is not None and rule.once not in rule.sets:
                raise ValueError(f"One-time rule must set its own marker {key}")
            if rule.gives and (rule.once is None or granted_items & rule.gives or any(
                items[item]["source"] != rule.command.target for item in rule.gives
            )):
                raise ValueError(f"Item grants require a one-time rule at the item's source {key}")
            granted_items.update(rule.gives)
            rules[key] = rule
        return cls(data["id"], data["version"], data["title"], data["start"],
                   data["goal"], locations, facts, items, rules, gates,
                   {location: tuple(symbols) for location, symbols in data.get("puzzle_symbols", {}).items()},
                   data.get("dialogue_style", {}))

    def start_state(self) -> State:
        return State(self.start)

    def journal(self, state: State) -> list[str]:
        return [f"{fact['kind']}: {fact['text']}" for key, fact in self.facts.items()
                if key in state.flags]

    def step(self, state: State, command: Command) -> Turn:
        if command.verb == "move":
            if command.target not in self.locations[state.location]["exits"]:
                return Turn(state, "You can't reach that location from here.", False)
            gate = self.gates.get((state.location, command.target))
            if gate is not None and gate not in state.flags:
                return Turn(state, "The way is locked.", False)
            return Turn(State(command.target, state.flags, state.inventory, state.turn + 1),
                        self.locations[command.target]["description"], True)

        rule = self.rules.get((state.location, command))
        if rule is None:
            if command.verb == "solve" and state.location in self.puzzle_symbols:
                return Turn(state, "The lockbox stays shut. That combination didn't match.", False)
            return Turn(state, "That action isn't available here.", False)
        if rule.once in state.flags:
            return Turn(state, "You've already done that.", False)
        if (not rule.requires <= state.flags
                or not (rule.needs_items | rule.consumes) <= state.inventory
                or (rule.needs_any_item and not rule.needs_any_item & state.inventory)):
            return Turn(state, rule.blocked, False)
        updated = State(
            state.location, state.flags | rule.sets,
            (state.inventory - rule.consumes) | rule.gives, state.turn + 1,
        )
        return Turn(updated, rule.message, True)
