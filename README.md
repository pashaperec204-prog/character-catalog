# Каталог персонажів

Тема 1. Консольний каталог персонажів Genshin Impact і власних карток. Потрібен Python 3.10 або новіший. Сторонні бібліотеки не потрібні.

[Дизайн-документ](docs/design.md)

## Запуск

Відкрийте термінал у папці проєкту. Для Windows:

```powershell
py -m character_catalog
```

На Linux і macOS використовуйте `python3 -m character_catalog`.

```text
catalog> refresh
catalog> list
catalog> show amber
catalog> portrait amber
catalog> create
catalog> show user:star-keeper
catalog> exit
```

Під час `create` введіть код `star-keeper` або власний код, ім’я, опис і посилання на зображення. Дані зберігаються у `~/.character_catalog/catalog.json`. Для іншого файла використайте `py -m character_catalog --data-file ./catalog.json`.

## Бізнес-компонент

`character_catalog/parser.py` перетворює JSON Genshin API на моделі персонажа, талантів і сузір’їв. Для майбутнього графічного інтерфейсу доступні `CharacterCatalog.list_entries()` і `Character.to_view_data()`. Поля, правила валідації та приклад використання описані в [дизайн-документі](docs/design.md#бізнес-компонент-парсинг-даних-для-графічного-інтерфейсу).

## Кеш портретів

`portrait amber` завантажує портрет у папку `portraits/` поруч із JSON-сховищем і показує шлях до файла. Наступні виклики використовують локальну копію, навіть після перезапуску. Деталі описані в [дизайн-документі](docs/design.md#завантаження-та-кеш-портретів).

## Тестування

```powershell
py -m unittest discover -s tests -v
```
