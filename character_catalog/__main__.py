import argparse
from pathlib import Path

from .cli import CatalogCLI
from .genshin_api import GenshinApi
from .service import CharacterCatalog
from .storage import JsonCatalogStore


def main() -> None:
    parser = argparse.ArgumentParser(description="Консольний каталог персонажів")
    parser.add_argument(
        "--data-file", type=Path, metavar="PATH",
        default=Path.home() / ".character_catalog" / "catalog.json",
        help="шлях до локального JSON-сховища",
    )
    args = parser.parse_args()
    try:
        catalog = CharacterCatalog(GenshinApi(), JsonCatalogStore(args.data_file))
    except (OSError, ValueError) as error:
        parser.error(str(error))
    CatalogCLI(catalog).run()


if __name__ == "__main__":
    main()
