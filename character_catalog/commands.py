import shlex
from collections.abc import Callable
from dataclasses import dataclass


@dataclass(frozen=True)
class Command:
    """Command: a registered action that the CLI can invoke by name."""

    handler: Callable[[list[str]], object]
    description: str

    def execute(self, args: list[str]) -> None:
        self.handler(args)


class CommandRegistry:
    def __init__(self, output=print):
        self._output = output
        self._commands: dict[str, Command] = {}

    def register(self, name, handler, description):
        self._commands[name] = Command(handler, description)

    def execute(self, line):
        try:
            lexer = shlex.shlex(line, posix=True)
            lexer.whitespace_split = True
            lexer.commenters = ""
            lexer.escape = ""
            parts = list(lexer)
        except ValueError as error:
            self._output(f"Помилка синтаксису: {error}")
            return
        if not parts:
            return
        name, *args = parts
        if name == "help":
            self.help()
            return
        command = self._commands.get(name)
        if command is None:
            self._output(f"Невідома команда: {name}. Введіть help.")
            return
        try:
            command.execute(args)
        except (OSError, ValueError) as error:
            self._output(f"Помилка: {error}")

    def help(self):
        for name, command in sorted(self._commands.items()):
            self._output(f"{name:<12} {command.description}")
        self._output("help         показати список команд")

