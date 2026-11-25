import asyncio
import sqlite3
from dataclasses import replace

from rich.text import Text
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Footer, Input, OptionList, RichLog, Static

from .__main__ import COMMAND_HELP
from .dialogue import (
    VOICE_SELECTION_PROMPT, DialogueProvider, available_replies, conversation_topics, rewrite_choice,
)
from .engine import Character, Command, Evidence, Pack, State
from .saves import Save
from .splash import Startup


class AdventurePanel(ModalScreen):
    BINDINGS = [("escape", "close", "Back")]

    def action_close(self):
        self.dismiss()


class TravelMap(AdventurePanel):
    def __init__(self, pack: Pack, state: State):
        super().__init__()
        self.pack = pack
        self.state = state
        self.exits = pack.locations[state.location]["exits"]

    def compose(self) -> ComposeResult:
        with Vertical(classes="panel"):
            yield Static("Map  /  Arrows select · Enter travels", classes="panel_title")
            yield Static(Text("  @ " + self.pack.locations[self.state.location]["name"]))
            options = []
            for index, destination in enumerate(self.exits):
                connector = "└─" if index == len(self.exits) - 1 else "├─"
                flag = self.pack.gates.get((self.state.location, destination))
                locked = flag is not None and flag not in self.state.flags
                name = self.pack.locations[destination]["name"]
                options.append(Text(f"  {connector} {name}" + ("  [locked]" if locked else "")))
            yield OptionList(*options)
            yield Footer()

    def on_option_list_option_selected(self, event: OptionList.OptionSelected):
        self.dismiss(Command("move", self.exits[event.option_index]))


class Lockbox(AdventurePanel):
    BINDINGS = [("backspace", "undo", "Undo"), ("f5", "try_lock", "Try combination")]
    ENGRAVINGS = {"fish": "≋", "moon": "☾", "reed": "╎"}

    def __init__(self, pack: Pack, state: State, symbols: tuple[str, ...]):
        super().__init__()
        self.pack = pack
        self.state = state
        self.symbols = symbols
        self.chosen: list[str] = []

    def compose(self) -> ComposeResult:
        with Vertical(classes="panel"):
            yield Static("Riverside lockbox", classes="panel_title")
            yield Static("Set the engraved slots from left to right.")
            yield Static(id="slots")
            yield OptionList(*(Text(f"{self.ENGRAVINGS.get(symbol, '◇')}  {symbol.title()}")
                               for symbol in self.symbols), id="engravings")
            yield Static(id="lock-feedback")
            with Horizontal(id="lock-controls"):
                yield Button("Try combination", id="try-lock", variant="primary")
                yield Button("Undo", id="undo-lock")
                yield Button("Reset", id="reset-lock")
            yield Footer()

    def on_mount(self):
        self.show_slots()
        self.query_one(OptionList).focus()

    def show_slots(self):
        slots = [f"[ {self.ENGRAVINGS.get(symbol, '◇')} {symbol.title()} ]" for symbol in self.chosen]
        slots += ["[   ·   ]"] * (len(self.symbols) - len(self.chosen))
        self.query_one("#slots", Static).update(Text(" ".join(slots), style="bold #e4bd73"))
        self.query_one("#try-lock", Button).disabled = len(self.chosen) < len(self.symbols)
        self.query_one("#undo-lock", Button).disabled = not self.chosen
        self.query_one("#reset-lock", Button).disabled = not self.chosen
        self.query_one("#lock-feedback", Static).update("")

    def action_undo(self):
        if self.chosen:
            self.chosen.pop()
            self.show_slots()

    def on_option_list_option_selected(self, event: OptionList.OptionSelected):
        if len(self.chosen) < len(self.symbols):
            self.chosen.append(self.symbols[event.option_index])
            self.show_slots()

    def action_try_lock(self):
        if len(self.chosen) != len(self.symbols):
            return
        command = Command("solve", " ".join(self.chosen))
        result = self.pack.step(self.state, command)
        if result.accepted:
            self.dismiss(command)
        else:
            self.query_one("#lock-feedback", Static).update(Text(result.message, style="#f2a78e"))

    def on_button_pressed(self, event: Button.Pressed):
        if event.button.id == "try-lock":
            self.action_try_lock()
        elif event.button.id == "undo-lock":
            self.action_undo()
            self.query_one(OptionList).focus()
        elif event.button.id == "reset-lock":
            self.chosen.clear()
            self.show_slots()
            self.query_one(OptionList).focus()


class EvidenceBoard(AdventurePanel):
    def __init__(self, pack: Pack, state: State, can_converse: bool):
        super().__init__()
        self.pack = pack
        self.state = state
        self.can_converse = can_converse
        self.entries = pack.evidence(state)

    def compose(self) -> ComposeResult:
        with Vertical(classes="panel reference-board"):
            yield Static("Evidence board", classes="panel_title")
            if self.entries:
                with Horizontal(classes="reference-body"):
                    yield OptionList(*(Text(entry.title) for entry in self.entries),
                                     id="evidence-list", classes="reference-list")
                    yield RichLog(wrap=True, id="clues", classes="reference-details")
                yield Button("Ask witness", id="evidence-ask", variant="primary", disabled=True)
            else:
                yield Static("No clues discovered yet.")
            yield Footer()

    def on_mount(self):
        if self.entries:
            self.show_entry(self.entries[0])
            self.query_one("#evidence-list", OptionList).focus()

    def show_entry(self, entry: Evidence):
        board = self.query_one("#clues", RichLog)
        board.clear()
        color = "#e4bd73" if entry.kind == "Evidence" else "#8bb498"
        board.write(Text(f"{entry.kind} · {entry.certainty_label}", style=f"bold {color}"))
        if entry.source:
            board.write(Text(f"Source  {entry.source}"))
        if entry.location:
            location = self.pack.locations[entry.location]["name"]
            board.write(Text(f"Location  {location}"))
        board.write(Text(entry.text))
        link = self.query_one("#evidence-ask", Button)
        link.label = f"Ask {entry.witness.title()}" if entry.witness else "Ask witness"
        link.disabled = not (self.can_converse and entry.witness and entry.location == self.state.location)
        if entry.witness and entry.question:
            board.write(Text(f"Follow-up  {entry.question}", style="#8bb498"))
            if entry.location != self.state.location:
                board.write(Text(f"Find {entry.witness.title()} at {location} to ask."))
        board.scroll_home(animate=False)

    def on_option_list_option_highlighted(self, event: OptionList.OptionHighlighted):
        self.show_entry(self.entries[event.option_index])

    def on_button_pressed(self, event: Button.Pressed):
        selected = self.query_one("#evidence-list", OptionList).highlighted
        if event.button.id == "evidence-ask" and selected is not None:
            entry = self.entries[selected]
            if self.can_converse and entry.witness and entry.location == self.state.location:
                self.dismiss(entry)


class CharacterBoard(AdventurePanel):
    def __init__(self, pack: Pack, state: State, can_converse: bool):
        super().__init__()
        self.pack = pack
        self.state = state
        self.can_converse = can_converse
        self.characters = pack.characters()

    def compose(self) -> ComposeResult:
        with Vertical(classes="panel reference-board"):
            yield Static("Characters", classes="panel_title")
            if self.characters:
                with Horizontal(classes="reference-body"):
                    yield OptionList(*(Text(character.name) for character in self.characters),
                                     id="character-list", classes="reference-list")
                    yield RichLog(wrap=True, id="character-details", classes="reference-details")
                yield Button("Talk", id="character-talk", variant="primary", disabled=True)
            else:
                yield Static("There are no characters to list.")
            yield Footer()

    def on_mount(self):
        if self.characters:
            self.show_character(self.characters[0])
            self.query_one("#character-list", OptionList).focus()

    def show_character(self, character: Character):
        board = self.query_one("#character-details", RichLog)
        board.clear()
        board.write(Text(character.name, style="bold #e4bd73"))
        locations = ", ".join(self.pack.locations[key]["name"] for key in character.locations)
        nearby = self.state.location in character.locations
        board.write(Text(f"Find at  {locations}" + (" · Here now" if nearby else ""), style="#8bb498"))
        board.write(Text("What you've learned", style="bold"))
        entries = self.pack.character_evidence(self.state, character.id)
        if not entries:
            board.write(Text("No clues learned yet."))
        for entry in entries:
            board.write(Text(f"{entry.title} · {entry.certainty_label}", style="#8bb498"))
            board.write(Text(entry.text))
        board.scroll_home(animate=False)
        button = self.query_one("#character-talk", Button)
        button.label = f"Talk to {character.name}"
        button.disabled = not (self.can_converse and nearby)

    def on_option_list_option_highlighted(self, event: OptionList.OptionHighlighted):
        self.show_character(self.characters[event.option_index])

    def on_button_pressed(self, event: Button.Pressed):
        selected = self.query_one("#character-list", OptionList).highlighted
        if event.button.id == "character-talk" and selected is not None:
            character = self.characters[selected]
            if self.can_converse and self.state.location in character.locations:
                self.dismiss(character)


class Conversation(AdventurePanel):
    def __init__(self, npc: str, topics: list[tuple[str, str]], history: list[Text], question: str = ""):
        super().__init__()
        self.npc = npc
        self.topics = topics
        self.history = history
        self.question = question

    def compose(self) -> ComposeResult:
        with Vertical(classes="panel conversation"):
            yield Static(f"Talking to {self.npc.title()}", classes="panel_title")
            with Horizontal(id="conversation-body"):
                yield RichLog(id="exchanges", wrap=True)
                with Vertical(id="conversation-topics"):
                    yield Static("Topics")
                    yield OptionList(*(Text(label) for label, _ in self.topics), id="topics")
            yield Input(value=self.question, placeholder=f"Ask {self.npc.title()} a question", id="question")
            yield Footer()

    def on_mount(self):
        for line in self.history:
            self.query_one("#exchanges", RichLog).write(line)
        field = self.query_one("#question", Input)
        field.focus()
        field.cursor_position = len(field.value)

    def write(self, line: Text):
        self.history.append(line)
        del self.history[:-24]
        self.query_one("#exchanges", RichLog).write(line)

    def on_input_submitted(self, event: Input.Submitted):
        event.stop()
        question = event.value.strip()
        if question:
            event.input.clear()
            self.app.ask(f"{self.npc} {question}")

    def on_option_list_option_selected(self, event: OptionList.OptionSelected):
        event.stop()
        self.app.ask(f"{self.npc} {self.topics[event.option_index][1]}")
        self.query_one("#question", Input).focus()

    def action_close(self):
        self.app.action_cancel_dialogue()
        self.dismiss()


class Adventure(App):
    ENABLE_COMMAND_PALETTE = False
    BINDINGS = [
        Binding("f2", "map", "Map"),
        Binding("f3", "journal", "Evidence"),
        Binding("f4", "puzzle", "Lockbox"),
        Binding("f6", "characters", "Characters"),
        Binding("ctrl+q", "quit", "Quit"),
        Binding("escape", "cancel_dialogue", show=False),
        Binding("up", "history_up", show=False),
        Binding("down", "history_down", show=False),
    ]
    CSS = """
    Screen { background: #111813; color: #e0dfcd; }
    #status { height: auto; min-height: 1; padding: 0 2; background: #25372a; color: #b6d5ae; }
    #play-area { height: 1fr; }
    #narrative { width: 1fr; }
    #story { height: 1fr; padding: 1 2; }
    #sidebar { width: 29%; min-width: 18; max-width: 30; padding: 0 1;
        border-left: solid #49644c; background: #19231b; }
    #sidebar Static { height: 1; color: #e4bd73; text-style: bold; }
    #views { height: auto; }
    #local-actions { height: 1fr; }
    #command { margin: 0 1; }
    Footer { background: #25372a; }
    AdventurePanel { align: center middle; }
    .panel { width: 72; max-width: 96%; height: auto; max-height: 90%;
        border: round #8aa986; background: #19231b; padding: 0 1; }
    .panel_title { height: auto; padding: 1 1; color: #e4bd73; text-style: bold; }
    .panel OptionList { height: auto; max-height: 10; }
    #slots { padding: 1 1; background: #353022; }
    #lock-feedback { height: auto; }
    #lock-controls { height: auto; }
    #lock-controls Button { min-width: 7; margin-right: 1; }
    .reference-board { width: 86; }
    .reference-body { height: 11; }
    .reference-board .reference-list { width: 35%; min-width: 18; height: 100%; max-height: 100%; }
    .reference-details { width: 1fr; height: 100%; padding: 0 1; border-left: solid #49644c; }
    .conversation { width: 86; height: 20; }
    #conversation-body { height: 1fr; min-height: 3; }
    #exchanges { width: 1fr; padding: 0 1; }
    #conversation-topics { width: 29%; min-width: 17; padding: 0 1; border-left: solid #49644c; }
    #conversation-topics Static { height: 1; color: #e4bd73; }
    #conversation-topics #topics { height: 1fr; max-height: 100%; }
    """

    def __init__(self, pack: Pack, save: Save, *, provider: DialogueProvider | None = None,
                 show_startup: bool = True, character_voice: bool = False):
        super().__init__()
        self.pack = pack
        self.save = save
        self.state = save.load_or_start(pack)
        self.history: list[str] = []
        self.history_position = 0
        self.draft = ""
        self.local_actions: list[Command] = []
        self.provider = provider
        self.character_voice = character_voice
        self.dialogue_worker = None
        self.conversation_history: dict[str, list[Text]] = {}
        self.previous_turn: dict[str, dict[str, str]] = {}
        self.preload_worker = None
        self.preload_finished = asyncio.Event()
        self.preload_succeeded = False
        self.show_startup = show_startup

    def compose(self) -> ComposeResult:
        yield Static(id="status")
        with Horizontal(id="play-area"):
            with Vertical(id="narrative"):
                yield RichLog(id="story", wrap=True)
                yield Input(placeholder="Type a command or /help", id="command")
            with Vertical(id="sidebar"):
                yield Static("Views")
                yield OptionList("Map", "Evidence board", "Inventory", "Characters", id="views")
                yield Static("Actions here")
                yield OptionList(id="local-actions")
        yield Footer()

    async def on_mount(self):
        self.write(self.pack.title, "bold #e4bd73")
        for verb, target, message in self.save.recent_events(self.state.turn):
            self.write(f"> {verb} {target}".rstrip(), "#8bb498")
            self.write(message)
        self.look()
        self.update_status()
        self.query_one(Input).focus()
        if self.show_startup:
            status = "Loading local model…" if self.provider else ""
            await self.push_screen(Startup(self.pack.title, status))
            if self.provider:
                self.preload_worker = self.run_worker(self.preload_model())

    async def preload_model(self):
        try:
            await asyncio.to_thread(self.provider.preload)
            self.preload_succeeded = True
        except (OSError, ValueError):
            if isinstance(self.screen, Startup):
                self.screen.set_model_status("Model unavailable · scripted dialogue ready")
            self.write("Model preload failed. /ask can retry or use scripted dialogue.", "#8bb498")
        else:
            if isinstance(self.screen, Startup):
                self.screen.set_model_status("Local model ready")
            else:
                self.write("Local model ready.", "#8bb498")
        finally:
            self.preload_finished.set()

    def write(self, message: str, style: str = ""):
        line = Text(message, style=style)
        self.screen_stack[0].query_one("#story", RichLog).write(line)
        if isinstance(self.screen, Conversation) and not message.startswith("> talk "):
            self.screen.write(line)

    def update_status(self):
        location = self.pack.locations[self.state.location]["name"]
        progress = "Mystery solved" if self.pack.goal in self.state.flags else "Autosave on"
        main = self.screen_stack[0]
        main.query_one("#status", Static).update(Text(f"{location}  /  Turn {self.state.turn}  /  {progress}"))
        actions = main.query_one("#local-actions", OptionList)
        selected = actions.highlighted
        self.local_actions = [Command("look", "")]
        if self.pack.goal not in self.state.flags:
            if self.state.location in self.pack.puzzle_symbols:
                self.local_actions.append(Command("puzzle", ""))
            self.local_actions.extend(
                command for (location_id, command), rule in self.pack.rules.items()
                if location_id == self.state.location and command.verb != "solve"
                and rule.once not in self.state.flags
            )
        actions.clear_options()
        actions.add_options(
            Text("Look around" if command.verb == "look" else
                 "Try lockbox" if command.verb == "puzzle" else
                 f"Talk to {command.target.title()}" if command.verb == "talk" else
                 f"{command.verb.title()} {command.target.replace('_', ' ').title()}")
            for command in self.local_actions
        )
        actions.highlighted = min(selected or 0, len(self.local_actions) - 1)

    def look(self):
        location = self.pack.locations[self.state.location]
        self.write(location["description"])
        self.write("Exits  " + ", ".join(location["exits"]), "#8bb498")

    def action_map(self):
        self.push_screen(TravelMap(self.pack, self.state), self.apply_command)

    def action_journal(self):
        can_converse = self.provider is not None and self.pack.goal not in self.state.flags
        self.push_screen(EvidenceBoard(self.pack, self.state, can_converse), self.follow_evidence)

    def action_characters(self):
        can_converse = self.provider is not None and self.pack.goal not in self.state.flags
        self.push_screen(CharacterBoard(self.pack, self.state, can_converse), self.follow_character)

    def follow_character(self, character: Character | None):
        if character is not None and self.state.location in character.locations and self.pack.goal not in self.state.flags:
            self.open_conversation(Command("talk", character.id))

    def follow_evidence(self, entry: Evidence | None):
        if (entry is not None and entry.id in self.state.flags and entry.witness
                and self.state.location == entry.location and self.pack.goal not in self.state.flags):
            self.open_conversation(Command("talk", entry.witness), question=entry.question or "")

    def action_puzzle(self):
        symbols = self.pack.puzzle_symbols.get(self.state.location)
        if symbols:
            self.push_screen(Lockbox(self.pack, self.state, symbols), self.apply_command)
        else:
            self.write("There is no lockbox here.")

    def open_conversation(self, command: Command, *, question: str = ""):
        preview = self.pack.step(self.state, command)
        if not preview.accepted:
            self.write(preview.message)
            return
        npc = command.target
        replies = available_replies(self.pack, self.state, npc, preview.message, focus=self.character_voice)
        topics = conversation_topics(npc, replies, self.pack)
        self.push_screen(Conversation(npc, topics, self.conversation_history.setdefault(npc, []), question))

    def browse_history(self, offset: int):
        field = self.query_one(Input)
        if not field.has_focus or not self.history:
            return
        if self.history_position == len(self.history):
            self.draft = field.value
        self.history_position = max(0, min(len(self.history), self.history_position + offset))
        field.value = self.draft if self.history_position == len(self.history) else self.history[self.history_position]
        field.cursor_position = len(field.value)

    def action_history_up(self):
        self.browse_history(-1)

    def action_history_down(self):
        self.browse_history(1)

    def on_input_submitted(self, event: Input.Submitted):
        entered = event.value.strip()
        event.input.clear()
        if not entered:
            return
        self.history.append(entered)
        self.history_position = len(self.history)
        self.draft = ""
        verb, _, target = entered.lstrip("/").partition(" ")
        verb = verb.lower()
        self.dispatch(Command(verb, target.strip() if verb == "ask" else " ".join(target.lower().split())))

    def on_option_list_option_selected(self, event: OptionList.OptionSelected):
        if event.option_list.id == "views":
            self.dispatch(Command(("map", "journal", "inventory", "characters")[event.option_index], ""))
        elif event.option_list.id == "local-actions":
            self.dispatch(self.local_actions[event.option_index])

    def dispatch(self, command: Command):
        match command.verb:
            case "quit":
                self.exit()
            case "map":
                self.action_map()
            case "journal":
                self.action_journal()
            case "characters":
                self.action_characters()
            case "puzzle":
                self.action_puzzle()
            case "try" if command.target == "lockbox":
                self.action_puzzle()
            case "help":
                self.write(COMMAND_HELP + "\n/map, /journal, /characters and /puzzle open interactive views."
                           "\nType try lockbox at the river landing to open the puzzle."
                           "\n/ask <person> <question> opens dialogue. Esc cancels a pending reply.")
            case "look":
                self.look()
            case "inventory":
                names = [self.pack.items[item]["name"] for item in sorted(self.state.inventory)]
                self.write(", ".join(names) or "Inventory is empty.")
            case "ask":
                self.ask(command.target)
            case "talk" if self.provider and self.pack.goal not in self.state.flags:
                self.open_conversation(command)
            case _:
                self.apply_command(command)

    def ask(self, target: str):
        parts = target.split(maxsplit=1)
        if len(parts) != 2:
            self.write("Use /ask <person> <question>.")
            return
        npc, question = parts[0].lower(), parts[1]
        if self.pack.goal in self.state.flags:
            self.write("The mystery is solved. You can still review the evidence.")
            return
        command = Command("talk", npc)
        preview = self.pack.step(self.state, command)
        if not preview.accepted:
            self.write(preview.message)
            return
        if self.provider is None:
            self.apply_command(command)
            return
        if self.dialogue_worker and not self.dialogue_worker.is_finished:
            self.write("A reply is pending. Press Esc to cancel it.")
            return
        self.write(f"> Ask {npc.title()}: {question}", "#8bb498")
        if self.preload_worker and not self.preload_worker.is_finished:
            self.write("Waiting for the local model to finish loading…", "#8bb498")
        else:
            self.write(f"{npc.title()} considers your question…", "#8bb498")
        self.dialogue_worker = self.run_worker(self.answer(command, question, self.state, preview.message))

    def action_cancel_dialogue(self):
        if self.dialogue_worker and not self.dialogue_worker.is_finished:
            self.dialogue_worker.cancel()
            self.write("Dialogue cancelled.", "#8bb498")

    async def answer(self, command: Command, question: str, snapshot: State, greeting: str):
        npc = command.target
        replies = available_replies(self.pack, snapshot, npc, greeting, focus=self.character_voice)
        drafted = None
        try:
            if self.preload_worker and not self.preload_worker.is_finished:
                await self.preload_finished.wait()
                if not self.preload_succeeded:
                    raise ValueError("Model preload failed.")
                if self.state != snapshot:
                    self.write("The conversation ended before the reply arrived.", "#8bb498")
                    return
            options = {"prompt": VOICE_SELECTION_PROMPT} if self.character_voice else {}
            if isinstance(self.screen, Conversation) and npc in self.previous_turn:
                options["previous"] = self.previous_turn[npc]
            choice = await asyncio.to_thread(self.provider.choose, question[:1000], replies, **options)
            if choice not in replies:
                raise ValueError("Unknown dialogue choice.")
        except (OSError, ValueError, KeyError, TypeError, AttributeError):
            choice = "introduce"
            self.write("Local dialogue unavailable. Using the scripted reply.", "#8bb498")
        else:
            if self.character_voice and choice != "unsure" and self.state == snapshot:
                line = replies[choice]
                try:
                    line = await asyncio.to_thread(
                        rewrite_choice, self.provider, self.pack, snapshot, npc, choice, question[:1000], line
                    )
                except (OSError, ValueError, KeyError, TypeError, AttributeError):
                    self.write("Voice rewrite unavailable. Using the scripted reply.", "#8bb498")
                if line != greeting:
                    drafted = f"{npc.title()}: {line}"
        if self.state != snapshot:
            self.write("The conversation ended before the reply arrived.", "#8bb498")
            return
        if isinstance(self.screen, Conversation) and choice != "unsure":
            self.previous_turn[npc] = {"question": question[:1000], "approved_reply": replies[choice]}
        if choice == "introduce":
            self.apply_command(command, dialogue=drafted)
        else:
            self.write(drafted or f"{command.target.title()}: {replies[choice]}")

    def apply_command(self, command: Command | None, *, dialogue: str | None = None):
        if command is None:
            return
        if self.pack.goal in self.state.flags:
            self.write("The mystery is solved. You can still review the evidence.")
            return
        self.write(f"> {command.verb} {command.target}".rstrip(), "#8bb498")
        result = self.pack.step(self.state, command)
        if result.accepted and dialogue is not None:
            result = replace(result, message=dialogue)
        try:
            self.save.commit(self.state, command, result)
        except (ValueError, sqlite3.Error) as error:
            self.write(f"Could not save turn. {error}", "#f2a78e")
            return
        self.state = result.state
        self.write(result.message, "" if result.accepted else "#f2a78e")
        self.update_status()
