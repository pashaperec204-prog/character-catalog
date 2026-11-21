from collections.abc import Sequence
from hashlib import sha256
from http.client import HTTPException
from pathlib import Path
from tempfile import NamedTemporaryFile
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from .model import validate_image_url


class PortraitError(ValueError):
    pass


class PortraitCache:
    """Cache HTTP(S) images by URL across catalog sessions."""

    EXTENSIONS = (".jpg", ".png", ".webp", ".gif")
    MAX_BYTES = 10 * 1024 * 1024

    def __init__(self, directory: Path, timeout: float = 8):
        self.directory = directory
        self.timeout = timeout

    def get(self, urls: Sequence[str]) -> tuple[Path, bool]:
        """Return the local path and whether it was already cached."""
        if not urls:
            raise PortraitError("Посилання на портрет відсутнє.")
        for url in urls:
            validate_image_url(url)
            prefix = self._key(url)
            for extension in self.EXTENSIONS:
                file = self.directory / (prefix + extension)
                try:
                    with file.open("rb") as stream:
                        if self._extension(stream.read(16)) == extension:
                            return file, True
                except FileNotFoundError:
                    continue

        errors = []
        for url in urls:
            try:
                data, extension = self._download(url)
            except PortraitError as error:
                errors.append(str(error))
                continue
            file = self.directory / (self._key(url) + extension)
            self._write(file, data)
            return file, False
        raise PortraitError("Не вдалося завантажити портрет. " + " ".join(dict.fromkeys(errors)))

    @staticmethod
    def _key(url: str) -> str:
        return sha256(url.encode("utf-8")).hexdigest()

    def _download(self, url: str) -> tuple[bytes, str]:
        request = Request(url, headers={"User-Agent": "Character-Catalog", "Accept": "image/*"})
        try:
            with urlopen(request, timeout=self.timeout) as response:
                content_length = response.headers.get("Content-Length", "")
                size = int(content_length) if content_length.isdecimal() else None
                if size is not None and size > self.MAX_BYTES:
                    raise PortraitError("Портрет перевищує обмеження 10 МіБ.")
                data = response.read(self.MAX_BYTES + 1)
        except HTTPError as error:
            raise PortraitError(f"Сервер повернув HTTP {error.code}.") from error
        except (OSError, HTTPException) as error:
            raise PortraitError("Не вдалося прочитати відповідь сервера зображень.") from error

        if len(data) > self.MAX_BYTES:
            raise PortraitError("Портрет перевищує обмеження 10 МіБ.")
        if size is not None and len(data) != size:
            raise PortraitError("Сервер повернув неповне зображення.")
        extension = self._extension(data)
        if extension is None:
            raise PortraitError("Очікується зображення JPEG, PNG, WebP або GIF.")
        return data, extension

    @staticmethod
    def _extension(data: bytes) -> str | None:
        if data.startswith(b"\x89PNG\r\n\x1a\n"):
            return ".png"
        if data.startswith(b"\xff\xd8\xff"):
            return ".jpg"
        if data.startswith((b"GIF87a", b"GIF89a")):
            return ".gif"
        if data.startswith(b"RIFF") and data[8:12] == b"WEBP":
            return ".webp"
        return None

    def _write(self, file: Path, data: bytes) -> None:
        self.directory.mkdir(parents=True, exist_ok=True)
        temporary = None
        try:
            # Replace atomically so readers cannot see half a download.
            with NamedTemporaryFile(dir=self.directory, delete=False) as stream:
                temporary = Path(stream.name)
                stream.write(data)
            temporary.replace(file)
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)
