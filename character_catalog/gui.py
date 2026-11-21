import argparse
import logging
import sys
from pathlib import Path
from threading import Event

from PySide6.QtCore import QObject, QRunnable, QThreadPool, QTimer, Qt, Signal, Slot
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QApplication, QFrame, QGridLayout, QHBoxLayout, QLabel, QLineEdit, QMainWindow,
    QMessageBox, QPushButton, QScrollArea, QSizePolicy, QVBoxLayout, QWidget,
)

from .genshin_api import GenshinApi
from .gui_data import CardPreview, load_preview
from .service import CharacterCatalog
from .storage import JsonCatalogStore


PAGE_SIZE = 6
ART_WIDTH, ART_HEIGHT = 142, 176

STYLE = """
QMainWindow { background: #131923; }
QWidget { color: #ebf0f6; font-family: "Segoe UI", "DejaVu Sans", sans-serif; font-size: 14px; }
QLabel#title { font-size: 35px; font-weight: 700; color: #faf2df; }
QLabel#status { color: #b2bdcd; }
QLabel#count { color: #d6bea0; font-weight: 600; }
QFrame#intro { background: #1d2635; border: 1px solid #37455a; border-radius: 14px; }
QLineEdit, QPushButton { padding: 8px 13px; min-height: 24px; border-radius: 8px; }
QLineEdit { background: #151d29; border: 1px solid #4b5b70; selection-background-color: #876a4d; }
QLineEdit:focus { border: 1px solid #efd09f; }
QPushButton { background: #283548; border: 1px solid #4b5b70; font-weight: 600; }
QPushButton#refresh { background: #efd09f; color: #282019; border: 1px solid #efd09f; }
QPushButton:hover { background: #354860; }
QPushButton#refresh:hover { background: #ffe0ad; }
QPushButton:focus { border: 2px solid #fbe4c0; }
QPushButton:disabled, QPushButton#refresh:disabled { background: #26303f; color: #9ba6b5; border: 1px solid #3d4859; }
QScrollArea { background: transparent; border: none; }
QWidget#cardGrid { background: #131923; }
QFrame#card { background: #1d2635; border: 1px solid #38465b; border-radius: 12px; }
QLabel#portrait { background: #0f1723; color: #a7b4c6; border: 1px solid #38465b; border-radius: 8px; }
QLabel#name { color: #fbf1df; font-size: 20px; font-weight: 700; }
QLabel#meta { color: #efd09f; font-size: 13px; font-weight: 600; }
QLabel#description { color: #c3cedd; font-size: 13px; }
QLabel#note { color: #9fb0c5; font-size: 12px; }
QScrollBar:vertical { background: #131923; width: 10px; margin: 1px; }
QScrollBar::handle:vertical { background: #536078; min-height: 35px; border-radius: 4px; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0px; }
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: none; }
"""


def text_label(value: str, name: str = "") -> QLabel:
    label = QLabel(value)
    label.setObjectName(name)
    label.setTextFormat(Qt.TextFormat.PlainText)
    return label


def shorten(text: str, limit: int = 125) -> str:
    text = " ".join(text.split())
    if len(text) <= limit:
        return text
    return text[:limit].rsplit(" ", 1)[0].rstrip() + "…"


class CharacterCard(QFrame):
    def __init__(self, preview: CardPreview):
        super().__init__()
        self.setObjectName("card")
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        row = QHBoxLayout(self)
        row.setContentsMargins(12, 12, 14, 12)
        row.setSpacing(15)

        portrait = text_label("", "portrait")
        portrait.setFixedSize(ART_WIDTH, ART_HEIGHT)
        portrait.setAlignment(Qt.AlignmentFlag.AlignCenter)
        portrait.setAccessibleName(f"Портрет {preview.label}")
        pixmap = QPixmap(str(preview.portrait)) if preview.portrait else QPixmap()
        if pixmap.isNull():
            portrait.setText("Немає\nпортрета")
        else:
            portrait.setPixmap(pixmap.scaled(
                ART_WIDTH - 4, ART_HEIGHT - 4,
                Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation,
            ))
        row.addWidget(portrait)

        content = QVBoxLayout()
        content.setSpacing(7)
        name = text_label(preview.label, "name")
        name.setWordWrap(True)
        content.addWidget(name)
        if preview.character is not None:
            card = preview.character
            details = [card.element, card.weapon, card.nation]
            if card.rarity:
                details.insert(0, f"{card.rarity} ★")
            fallback = "Власний персонаж" if preview.code.startswith("user:") else preview.code
            meta = text_label(" · ".join(value for value in details if value) or fallback, "meta")
            meta.setWordWrap(True)
            content.addWidget(meta)
            description = text_label(shorten(card.description), "description")
            description.setWordWrap(True)
            description.setToolTip(card.description)
            content.addWidget(description)
        if preview.message:
            note = text_label(preview.message, "note")
            note.setWordWrap(True)
            content.addWidget(note)
        content.addStretch(1)
        row.addLayout(content, 1)


class JobSignals(QObject):
    card_ready = Signal(object)
    succeeded = Signal(object)
    failed = Signal(str)


class CatalogJob(QRunnable):
    def __init__(self, action):
        super().__init__()
        self.action = action
        self.signals = JobSignals()

    def run(self):
        try:
            result = self.action(self.signals.card_ready.emit)
        except (OSError, ValueError) as error:
            self.signals.failed.emit(str(error))
        except Exception:
            logging.exception("Catalog job failed")
            self.signals.failed.emit("Не вдалося завершити завантаження.")
        else:
            self.signals.succeeded.emit(result)


class CatalogWindow(QMainWindow):
    def __init__(self, catalog: CharacterCatalog):
        super().__init__()
        self.catalog = catalog
        self.entries = []
        self.filtered = []
        self.shown = 0
        self.cards: list[CharacterCard] = []
        self._job = None
        self._on_success = None
        self._index_error = ""
        self._filter_pending = False
        self._closing = Event()
        self.pool = QThreadPool(self)
        self.pool.setMaxThreadCount(1)

        self.setWindowTitle("Каталог персонажів")
        self.setMinimumSize(740, 520)
        self.resize(1080, 760)
        self.setStyleSheet(STYLE)
        self._build_layout()
        QTimer.singleShot(0, self._start)

    def _build_layout(self):
        body = QWidget()
        self.setCentralWidget(body)
        outer = QVBoxLayout(body)
        outer.setContentsMargins(24, 23, 24, 18)
        outer.setSpacing(14)

        intro = QFrame(objectName="intro")
        header = QVBoxLayout(intro)
        header.setContentsMargins(19, 15, 19, 15)
        first = QHBoxLayout()
        first.addWidget(text_label("Каталог персонажів", "title"), 1)
        self.refresh_button = QPushButton("Оновити каталог", objectName="refresh")
        self.refresh_button.clicked.connect(self.refresh)
        first.addWidget(self.refresh_button)
        header.addLayout(first)
        controls = QHBoxLayout()
        self.search = QLineEdit()
        self.search.setPlaceholderText("Пошук за ім’ям або ID")
        self.search.setAccessibleName("Пошук персонажа")
        self.search.setClearButtonEnabled(True)
        self._search_timer = QTimer(self, singleShot=True, interval=250)
        self._search_timer.timeout.connect(self._filter_cards)
        self.search.textChanged.connect(lambda _: self._search_timer.start())
        self.search.returnPressed.connect(self._submit_search)
        controls.addWidget(self.search, 1)
        self.count = text_label("", "count")
        controls.addWidget(self.count)
        header.addLayout(controls)
        outer.addWidget(intro)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        content = QWidget(objectName="cardGrid")
        self.grid = QGridLayout(content)
        self.grid.setContentsMargins(0, 4, 7, 4)
        self.grid.setHorizontalSpacing(12)
        self.grid.setVerticalSpacing(12)
        self.grid.setColumnStretch(0, 1)
        self.grid.setColumnStretch(1, 1)
        self.grid.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.scroll.setWidget(content)
        outer.addWidget(self.scroll, 1)

        footer = QHBoxLayout()
        self.status = text_label("", "status")
        self.status.setWordWrap(True)
        footer.addWidget(self.status, 1)
        self.more = QPushButton("Показати ще")
        self.more.clicked.connect(self._load_page)
        footer.addWidget(self.more)
        outer.addLayout(footer)
        self.more.hide()

    def _start(self):
        self.entries = self.catalog.list_entries()
        if self.catalog.data.remote_ids:
            self._filter_cards()
        else:
            self.refresh()

    def refresh(self):
        if self._job is not None:
            return

        def load_index(_emit):
            try:
                self.catalog.refresh()
            except (OSError, ValueError) as error:
                return self.catalog.list_entries(), str(error)
            return self.catalog.list_entries(), ""

        self.status.setText("Оновлення каталогу…")
        self._run_job(load_index, self._index_ready)

    def _index_ready(self, result):
        self.entries, self._index_error = result
        self._filter_cards()

    def _submit_search(self):
        self._search_timer.stop()
        self._filter_cards()

    def _filter_cards(self):
        if self._job is not None:
            self._filter_pending = True
            return
        self._filter_pending = False
        query = self.search.text().strip().casefold()
        self.filtered = [
            entry for entry in self.entries
            if query in entry["label"].casefold() or query in entry["id"].casefold()
        ]
        for card in self.cards:
            self.grid.removeWidget(card)
            card.deleteLater()
        self.cards.clear()
        self.shown = 0
        self.scroll.verticalScrollBar().setValue(0)
        self._update_controls()
        if self.filtered:
            self._load_page()
        else:
            empty = "За цим пошуком нічого не знайдено." if query else "Каталог порожній."
            self._show_status(empty)

    def _load_page(self):
        if self._job is not None or self.shown >= len(self.filtered):
            return
        batch = self.filtered[self.shown:self.shown + PAGE_SIZE]
        self.status.setText("Завантаження карток…")

        def load_cards(emit):
            for entry in batch:
                if self._closing.is_set():
                    break
                emit(load_preview(self.catalog, entry))

        self._run_job(load_cards, self._page_ready)

    @Slot(object)
    def _append_card(self, preview: CardPreview):
        card = CharacterCard(preview)
        self.cards.append(card)
        self.grid.addWidget(card, self.shown // 2, self.shown % 2)
        self.shown += 1
        self._update_controls()

    def _page_ready(self, _result):
        self.entries = self.catalog.list_entries()
        if self._filter_pending:
            self._filter_cards()
            return
        self._show_status(f"Показано {self.shown} із {len(self.filtered)}.")

    def _show_status(self, text):
        if self._index_error:
            text = f"Оновлення недоступне. {text}"
        self.status.setToolTip(self._index_error)
        self.status.setText(text)

    def _run_job(self, action, on_success):
        job = CatalogJob(action)
        queued = Qt.ConnectionType.QueuedConnection
        job.signals.card_ready.connect(self._append_card, queued)
        job.signals.succeeded.connect(self._job_succeeded, queued)
        job.signals.failed.connect(self._job_failed, queued)
        self._job = job
        self._on_success = on_success
        self._update_controls()
        self.pool.start(job)

    @Slot(object)
    def _job_succeeded(self, result):
        on_success = self._on_success
        self._job, self._on_success = None, None
        self._update_controls()
        if not self._closing.is_set():
            on_success(result)

    @Slot(str)
    def _job_failed(self, message):
        self._job, self._on_success = None, None
        self._update_controls()
        self.status.setText(message)
        if self._filter_pending:
            self._filter_cards()

    def _update_controls(self):
        busy = self._job is not None
        self.refresh_button.setEnabled(not busy)
        self.more.setEnabled(not busy)
        self.more.setVisible(self.shown < len(self.filtered))
        self.count.setText(f"{self.shown} / {len(self.filtered)}")

    def closeEvent(self, event):
        self._closing.set()
        super().closeEvent(event)


def main() -> int:
    parser = argparse.ArgumentParser(description="Графічний каталог персонажів")
    parser.add_argument(
        "--data-file", type=Path, metavar="PATH",
        default=Path.home() / ".character_catalog" / "catalog.json",
        help="шлях до локального JSON-сховища",
    )
    args = parser.parse_args()
    app = QApplication(sys.argv[:1])
    try:
        catalog = CharacterCatalog(GenshinApi(), JsonCatalogStore(args.data_file))
    except (OSError, ValueError) as error:
        QMessageBox.critical(None, "Каталог персонажів", str(error))
        return 1
    window = CatalogWindow(catalog)
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
