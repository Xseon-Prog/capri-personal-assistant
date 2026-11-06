"""Local, foreground-window OCR for screen reading and bounded UI actions."""
from __future__ import annotations

import asyncio
import ctypes
import logging
import re
import unicodedata
from dataclasses import dataclass
from ctypes import wintypes

log = logging.getLogger("capri")


class ScreenReadError(RuntimeError):
    """The active window could not be safely captured or recognized."""


@dataclass(frozen=True)
class ScreenLine:
    text: str
    x: float
    y: float
    width: float
    height: float


@dataclass(frozen=True)
class ScreenRead:
    hwnd: int
    pid: int
    title: str
    left: int
    top: int
    width: int
    height: int
    image_width: int
    image_height: int
    lines: tuple[ScreenLine, ...]

    @property
    def text(self) -> str:
        return "\n".join(line.text for line in self.lines if line.text.strip())


def normalize_text(value: str) -> str:
    value = unicodedata.normalize("NFKC", (value or "").replace("ё", "е").replace("Ё", "Е")).casefold()
    value = re.sub(r"[^\w\s]", " ", value, flags=re.UNICODE)
    return re.sub(r"\s+", " ", value).strip()


def classify_screen_command(command: str) -> str | None:
    """Recognize only explicit screen-reading or save-then-exit requests."""
    text = normalize_text(command)
    if not text:
        return None
    has_save = re.search(r"\b(сохран\w*|save)\b", text)
    has_exit = re.search(r"\b(выйд\w*|закрой\w*|выход\w*|exit|quit)\b", text)
    if has_save and has_exit:
        return "save_exit"
    has_screen = re.search(r"\b(экран\w*|screen\w*)\b", text)
    has_read_intent = re.search(
        r"\b(проанализ\w*|анализ\w*|прочитай|прочитать|считай|перескаж\w*|"
        r"опиши|что написан\w*|что видн\w*)\b",
        text,
    )
    if has_screen and has_read_intent:
        return "summary"
    return None


def find_text_line(lines: tuple[ScreenLine, ...] | list[ScreenLine], targets: tuple[str, ...] | list[str]) -> ScreenLine | None:
    """Return a unique OCR line containing a target; prefer a unique exact line."""
    normalized_targets = {normalize_text(target) for target in targets if normalize_text(target)}
    if not normalized_targets:
        return None
    exact = [line for line in lines if normalize_text(line.text) in normalized_targets]
    if len(exact) == 1:
        return exact[0]
    if len(exact) > 1:
        return None
    matches = []
    for line in lines:
        line_text = normalize_text(line.text)
        if line_text and any(target in line_text for target in normalized_targets):
            matches.append(line)
    return matches[0] if len(matches) == 1 else None


def has_save_confirmation(text: str) -> bool:
    normalized = normalize_text(text)
    confirmations = (
        "игра сохранена", "игра сохранено", "успешно сохранена", "успешно сохранено",
        "сохранено", "сохранение завершено", "game saved", "saved successfully",
        "save complete", "save completed",
    )
    return any(phrase in normalized for phrase in confirmations)


def is_new_save_confirmation(previous_text: str, current_text: str) -> bool:
    """Do not mistake an already-visible save toast for confirmation of this save attempt."""
    return has_save_confirmation(current_text) and not has_save_confirmation(previous_text)


async def _recognize(image) -> tuple[ScreenLine, ...]:
    try:
        from PIL import Image
        from winrt.windows.graphics.imaging import BitmapPixelFormat, SoftwareBitmap
        from winrt.windows.media.ocr import OcrEngine
        from winrt.windows.storage.streams import DataWriter
    except ImportError as exc:
        raise ScreenReadError(
            "Компоненты Windows OCR не установлены. Запусти setup.bat, затем проверь зависимости."
        ) from exc

    red, green, blue, alpha = image.split()
    bgra = Image.merge("RGBA", (blue, green, red, alpha))
    bitmap = None
    try:
        writer = DataWriter()
        writer.write_bytes(list(bgra.tobytes()))
        bitmap = SoftwareBitmap(BitmapPixelFormat.BGRA8, image.width, image.height)
        bitmap.copy_from_buffer(writer.detach_buffer())
        engine = OcrEngine.try_create_from_user_profile_languages()
        if engine is None:
            raise ScreenReadError(
                "Windows OCR не нашёл языковой пакет профиля. Установи русский или английский язык распознавания в Windows."
            )
        result = await engine.recognize_async(bitmap)
        lines = []
        for item in result.lines:
            text = (item.text or "").strip()
            if not text:
                continue
            rect = item.bounding_rect
            lines.append(ScreenLine(text, float(rect.x), float(rect.y), float(rect.width), float(rect.height)))
        return tuple(lines)
    finally:
        if bitmap is not None:
            bitmap.close()
        bgra.close()
        for channel in (red, green, blue, alpha):
            channel.close()


def read_active_window(expected_pid: int | None = None) -> ScreenRead:
    """Capture and OCR the current target window without saving or uploading an image."""
    try:
        from PIL import Image, ImageGrab
        from . import automation
    except ImportError as exc:
        raise ScreenReadError("Не удалось загрузить локальные средства чтения экрана.") from exc

    hwnd = automation.target_window()
    if not hwnd:
        raise ScreenReadError("Не нашла активное окно для чтения.")
    user32 = ctypes.windll.user32
    rect = wintypes.RECT()
    if not user32.GetWindowRect(hwnd, ctypes.byref(rect)):
        raise ScreenReadError("Не удалось получить границы активного окна.")
    left, top, right, bottom = int(rect.left), int(rect.top), int(rect.right), int(rect.bottom)
    width, height = right - left, bottom - top
    if width < 40 or height < 40:
        raise ScreenReadError("Активное окно слишком мало для чтения.")

    process_id = wintypes.DWORD()
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(process_id))
    if expected_pid is not None and process_id.value != expected_pid:
        raise ScreenReadError("Активное приложение изменилось; дальнейшие действия остановлены.")

    try:
        captured = ImageGrab.grab(bbox=(left, top, right, bottom))
    except Exception as exc:
        raise ScreenReadError("Не удалось сделать снимок активного окна.") from exc
    image = captured.convert("RGBA")
    captured.close()
    image.thumbnail((1600, 1600), Image.Resampling.LANCZOS)
    image_width, image_height = image.size
    try:
        lines = asyncio.run(_recognize(image))
    except ScreenReadError:
        raise
    except Exception as exc:
        log.info("Windows OCR failed: %s", exc)
        raise ScreenReadError("Windows OCR не смог прочитать активное окно.") from exc
    finally:
        image.close()

    return ScreenRead(
        hwnd=int(hwnd), pid=int(process_id.value), title=automation.window_title(hwnd),
        left=left, top=top, width=width, height=height,
        image_width=image_width, image_height=image_height, lines=lines,
    )


def click_text_line(screen: ScreenRead, line: ScreenLine) -> bool:
    """Click only a uniquely recognized line in the same still-targeted window."""
    from . import automation

    if line not in screen.lines or automation.target_window() != screen.hwnd:
        return False
    if automation.window_title(screen.hwnd) != screen.title:
        return False
    if not automation.is_foreground(screen.hwnd) and not automation.focus(screen.hwnd):
        return False

    scale_x = screen.width / max(1, screen.image_width)
    scale_y = screen.height / max(1, screen.image_height)
    x = screen.left + round((line.x + line.width / 2) * scale_x)
    y = screen.top + round((line.y + line.height / 2) * scale_y)
    user32 = ctypes.windll.user32
    point = wintypes.POINT(x, y)
    under = user32.WindowFromPoint(point)
    if not under or user32.GetAncestor(under, 2) != screen.hwnd:
        return False

    old = wintypes.POINT()
    if not user32.GetCursorPos(ctypes.byref(old)) or not user32.SetCursorPos(x, y):
        return False
    try:
        user32.mouse_event(0x0002, 0, 0, 0, 0)
        user32.mouse_event(0x0004, 0, 0, 0, 0)
    finally:
        user32.SetCursorPos(old.x, old.y)
    return True
