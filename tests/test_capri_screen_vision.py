"""Pure tests for screen-command routing and OCR text matching."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from capri_app.screen_vision import (
    ScreenLine,
    classify_screen_command,
    find_text_line,
    has_save_confirmation,
    is_new_save_confirmation,
)


def main() -> None:
    assert classify_screen_command("проанализируй текст на экране и перескажи кратко без воды") == "summary"
    assert classify_screen_command("нажми клавишу esc и найди сохранить игру после сохранения выйди") == "save_exit"
    assert classify_screen_command("сохрани настройки") is None
    assert classify_screen_command("нажми esc") is None

    save = ScreenLine("СОХРАНИТЬ ИГРУ", 10, 20, 130, 24)
    assert find_text_line([save], ["сохранить игру", "save game"]) is save
    ambiguous = [
        ScreenLine("Нажми Сохранить игру сейчас", 0, 0, 100, 20),
        ScreenLine("Сохранить игру перед выходом", 0, 0, 100, 20),
    ]
    assert find_text_line(ambiguous, ["сохранить игру"]) is None
    assert has_save_confirmation("Игра сохранена")
    assert has_save_confirmation("Game saved")
    assert not has_save_confirmation("Сохранить игру")
    assert is_new_save_confirmation("Сохранить игру", "Game saved")
    assert not is_new_save_confirmation("Game saved", "Game saved")
    print("OK: screen OCR routing and matching")


if __name__ == "__main__":
    main()
