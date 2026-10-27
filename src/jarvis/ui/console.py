"""Rich-powered console presentation for the interactive Jarvis CLI."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from rich.console import Console
from rich.panel import Panel
from rich.status import Status
from rich.table import Table
from rich.text import Text

EXIT_COMMANDS = frozenset({"q", "quit", "exit", "выход"})
HELP_COMMANDS = frozenset({"help", "?", "помощь", "команды"})


class ConsoleUI:
    """Small presentation facade around a shared Rich console."""

    def __init__(self, console: Console | None = None) -> None:
        self.console = console or Console()

    def banner(self) -> None:
        """Print the startup banner as a Rich panel."""

        title = Text("J A R V I S", style="bold bright_cyan")
        subtitle = Text("голосовой ассистент · локально · офлайн", style="dim")
        body = Text.assemble(title, "\n", subtitle)
        self.console.print(
            Panel(
                body,
                title="[bold cyan]JARVIS[/bold cyan]",
                subtitle="[dim]local first[/dim]",
                border_style="bright_blue",
                padding=(1, 3),
                expand=False,
            )
        )

    def listening(self) -> None:
        """Show the colored listening indicator while the microphone captures."""

        self.console.print(Text("[Слушаю...]", style="bold green"))

    def thinking(self) -> Status:
        """Return a Rich status spinner for the transcription phase."""

        return self.console.status("[bold yellow]Думаю...[/bold yellow]", spinner="dots")

    def commands(self, skills: Iterable[Any]) -> None:
        """Print a table of registered skills and example commands."""

        table = Table(
            title="Зарегистрированные команды",
            title_style="bold cyan",
            header_style="bold white on blue",
            border_style="bright_blue",
            row_styles=["", "dim"],
        )
        table.add_column("Навык", style="bold cyan", no_wrap=True)
        table.add_column("Примеры команд", style="white")

        for skill in skills:
            name = str(getattr(skill, "name", "unknown"))
            examples = getattr(skill, "examples", [])
            if examples:
                value = " · ".join(str(example) for example in examples[:2])
            else:
                value = str(getattr(skill, "description", ""))
            table.add_row(name, value)

        self.console.print(table)

    def assistant(self, text: str, *, ok: bool = True) -> None:
        """Print an assistant answer with a colored speaker label."""

        prefix = Text("Джарвис:", style="bold cyan" if ok else "bold red")
        body = Text(text, style="white" if ok else "red")
        self.console.print(Text.assemble(prefix, " ", body))

    def info(self, text: str) -> None:
        self.console.print(Text(text, style="white"))

    def hint(self, text: str) -> None:
        self.console.print(Text(text, style="dim"))

    def error(self, text: str) -> None:
        self.console.print(Text(text, style="bold red"))

    def ask(self) -> str:
        return self.console.input("[bold green]Вы:[/bold green] ").strip()

    def goodbye(self) -> None:
        self.console.print()
        self.console.print(Text("До встречи. Джарвис завершает работу.", style="bold cyan"))


console_ui = ConsoleUI()
