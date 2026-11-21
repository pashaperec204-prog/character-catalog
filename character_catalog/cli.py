from .commands import CommandRegistry
from .service import CharacterCatalog


class CatalogCLI:
    def __init__(self, catalog: CharacterCatalog, input_func=input, output=print):
        self.catalog = catalog
        self.input = input_func
        self.output = output
        self.running = True
        self.commands = CommandRegistry(output)
        self.commands.register("refresh", self.refresh, "оновити список віддалених персонажів")
        self.commands.register("list", self.list_characters, "показати всі доступні ID персонажів")
        self.commands.register("show", self.show, "show <id> показати картку та посилання")
        self.commands.register("create", self.create, "створити персонажа через діалог")
        self.commands.register("exit", self.exit, "завершити роботу")

    def run(self) -> None:
        self.output("Каталог персонажів. Введіть help для списку команд.")
        while self.running:
            try:
                self.commands.execute(self.input("catalog> "))
            except (EOFError, KeyboardInterrupt):
                self.output("")
                break
        self.output("Роботу завершено.")

    @staticmethod
    def _count(args: list[str], expected: int, usage: str) -> None:
        if len(args) != expected:
            raise ValueError(f"Використання: {usage}")

    def refresh(self, args: list[str]) -> None:
        self._count(args, 0, "refresh")
        count = self.catalog.refresh()
        self.output(f"Оновлено. Віддалених персонажів: {count}.")
        self.list_characters([])

    def list_characters(self, args: list[str]) -> None:
        self._count(args, 0, "list")
        data = self.catalog.data
        if data.remote_ids:
            self.output(f"Джерело: {data.source}. Віддалених персонажів: {len(data.remote_ids)}.")
            for code in data.remote_ids:
                self.output(code)
        else:
            self.output("Список віддалених персонажів порожній. Виконайте refresh.")
        self.output(f"Створених персонажів: {len(data.custom_cards)}.")
        for code, card in sorted(data.custom_cards.items()):
            self.output(f"{code}  {card.name}")

    def show(self, args: list[str]) -> None:
        self._count(args, 1, "show <id>")
        card, cached = self.catalog.show(args[0].lower())
        self.output(f"{card.name} ({card.id})")
        self.output(f"Опис: {card.description}")
        for title, value in (
            ("Стихія", card.element), ("Регіон", card.nation), ("Зброя", card.weapon),
            ("Рідкість", card.rarity),
        ):
            if value:
                self.output(f"{title}: {value}")
        self.output(f"Графіка: {card.image_url}")
        if cached:
            self.output("Показано збережену локальну копію картки.")

    def create(self, args: list[str]) -> None:
        self._count(args, 0, "create")
        self.output("Введіть дані персонажа. Для скасування введіть /cancel у будь-якому полі.")
        values = []
        for prompt in (
            "Код (наприклад star-keeper): ", "Ім’я: ", "Опис: ", "URL зображення: ",
        ):
            try:
                value = self.input(prompt).strip()
            except KeyboardInterrupt:
                value = "/cancel"
            if value == "/cancel":
                self.output("Створення скасовано.")
                return
            if not value:
                raise ValueError("Усі поля обов’язкові.")
            values.append(value)
        card = self.catalog.create(values[0].lower(), *values[1:])
        self.output(f"Персонажа {card.id} створено й збережено.")

    def exit(self, args: list[str]) -> None:
        self._count(args, 0, "exit")
        self.running = False
