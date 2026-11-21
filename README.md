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
catalog> create
catalog> show user:star-keeper
catalog> exit
```

Під час `create` введіть код `star-keeper` або власний код, ім’я, опис і посилання на зображення. Дані зберігаються у `~/.character_catalog/catalog.json`. Для іншого файла використайте `py -m character_catalog --data-file ./catalog.json`.

## Тестування

```powershell
py -m unittest discover -s tests -v
```
