"""Apply Capri cyberpunk context menu + persistent on-screen avatar option.
Run from the extracted Capri project root with: py -3.13 tools\\apply_capri_menu_pin_v8.py
Only main.py and avatar.py are modified. Backups are created before writing.
"""
from __future__ import annotations

import ast
import datetime as dt
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MAIN = ROOT / "main.py"
AVATAR = ROOT / "avatar.py"
MARKER = "CAPRI_MENU_PIN_V8"

MENU_STYLE = '''    menu = QMenu()
    menu.setStyleSheet("""
        QMenu {
            background-color: #0a0612;
            color: #f8dce9;
            border: 1px solid #ff2260;
            padding: 6px 4px;
            font-family: "Segoe UI";
            font-size: 10pt;
        }
        QMenu::item {
            padding: 8px 30px 8px 14px;
            margin: 2px 4px;
            border: 1px solid transparent;
            border-radius: 3px;
        }
        QMenu::item:selected {
            background-color: #ff2260;
            color: #ffffff;
            border-color: #ff6f99;
        }
        QMenu::item:disabled {
            color: #28ff96;
            padding-top: 7px;
            padding-bottom: 7px;
        }
        QMenu::item:checked {
            background-color: #10251f;
            color: #28ff96;
        }
        QMenu::separator {
            height: 1px;
            background: #523044;
            margin: 5px 9px;
        }
        QMenu::indicator {
            width: 13px;
            height: 13px;
            margin-left: 7px;
        }
        QMenu::indicator:checked {
            background-color: #28ff96;
            border: 1px solid #28ff96;
        }
    """)
    _capri_menu_heading = QAction("CAPRI  //  QUICK MENU", menu)
    _capri_menu_heading.setEnabled(False)
    menu.addAction(_capri_menu_heading)
    menu.addSeparator()
    for title, fn in ('''

PIN_BRANCH = '''        if title == "PIN":
            pin_act = QAction("Оставаться на рабочем столе", menu)
            pin_act.setCheckable(True)
            pin_act.setChecked(bool(capri.cfg.get("pin_on_desktop", False)))

            def set_pinned(checked):
                enabled = bool(checked)
                capri.cfg["pin_on_desktop"] = enabled
                save_setting("pin_on_desktop", enabled)
                avatar.stay_visible = enabled
                if enabled:
                    avatar.hide_at = 0
                    avatar.summon()
                elif avatar.state == "visible" and avatar.mode == "idle":
                    avatar.hide_at = time.time() + avatar.hide_after

            pin_act.toggled.connect(set_pinned)
            menu.addAction(pin_act)
            menu.addSeparator()
            continue
        if title == "MIC":'''

SYNC_PIN = '''    def sync_pin_action():
        capri.reload_config_if_changed(speak=False)
        pin_act.blockSignals(True)
        pin_act.setChecked(bool(capri.cfg.get("pin_on_desktop", False)))
        pin_act.blockSignals(False)

    menu.aboutToShow.connect(sync_pin_action)

    tray = QSystemTrayIcon(tray_icon())'''


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"Cannot safely apply patch ({label}): expected one anchor, found {count}.")
    return text.replace(old, new, 1)


def make_main(text: str) -> str:
    if MARKER in text:
        raise RuntimeError("main.py already has the v8 marker; no changes were made.")
    text = replace_once(
        text,
        '    avatar.hide_after = float(cfg["hide_after_seconds"])\n',
        '    avatar.hide_after = float(cfg["hide_after_seconds"])\n'
        '    avatar.stay_visible = bool(cfg.get("pin_on_desktop", False))  # CAPRI_MENU_PIN_V8\n',
        "initialize pinned avatar",
    )
    text = replace_once(
        text,
        '    avatar.clicked.connect(capri.call_from_click)\n',
        '    avatar.clicked.connect(capri.call_from_click)\n'
        '    if avatar.stay_visible:\n'
        '        avatar.summon()\n',
        "show pinned avatar on startup",
    )
    text = replace_once(text, '    menu = QMenu()\n    for title, fn in (', MENU_STYLE, "style context menu")
    text = replace_once(
        text,
        '                      ("Спрятать", avatar.vanish),\n                      ("MIC", None),',
        '                      ("Спрятать", avatar.vanish),\n'
        '                      ("PIN", None),\n'
        '                      ("MIC", None),',
        "add pin action placeholder",
    )
    text = replace_once(
        text,
        '        if title == "MIC":',
        PIN_BRANCH,
        "add pin checkbox handler",
    )
    text = replace_once(text, '    tray = QSystemTrayIcon(tray_icon())', SYNC_PIN, "sync pin checkbox")
    # Add a stable marker for safe repeat detection.
    text = text.replace('    menu.setStyleSheet("""', '    # ' + MARKER + '\n    menu.setStyleSheet("""', 1)
    return text


def make_avatar(text: str) -> str:
    if MARKER in text:
        raise RuntimeError("avatar.py already has the v8 marker; no changes were made.")
    text = replace_once(
        text,
        '        self.hide_after = 12.0\n',
        '        self.hide_after = 12.0\n'
        '        self.stay_visible = False  # ' + MARKER + '\n',
        "add avatar pin state",
    )
    text = replace_once(
        text,
        '        self.hide_at = time.time() + self.hide_after if mode == "idle" else 0\n',
        '        self.hide_at = (time.time() + self.hide_after\n'
        '                        if mode == "idle" and not self.stay_visible else 0)  # ' + MARKER + '\n',
        "prevent idle timer when pinned",
    )
    text = replace_once(
        text,
        '        elif self.state == "visible" and self.hide_at and now > self.hide_at:\n',
        '        elif (self.state == "visible" and self.hide_at and now > self.hide_at\n'
        '              and not self.stay_visible):  # ' + MARKER + '\n',
        "guard automatic vanish",
    )
    return text


def main() -> int:
    if not MAIN.is_file() or not AVATAR.is_file():
        print("[Capri v8] Ошибка: запусти установщик из корня Capricorn, рядом с main.py и avatar.py.")
        return 2
    main_src = MAIN.read_text(encoding="utf-8-sig")
    avatar_src = AVATAR.read_text(encoding="utf-8-sig")
    try:
        next_main = make_main(main_src)
        next_avatar = make_avatar(avatar_src)
        ast.parse(next_main, filename=str(MAIN))
        ast.parse(next_avatar, filename=str(AVATAR))
    except Exception as exc:
        print(f"[Capri v8] Проверка не пройдена: {exc}")
        print("Файлы не изменены. Проверь совместимость версии проекта и пришли это сообщение.")
        return 1

    backup_dir = ROOT / "backups" / ("capri_menu_pin_v8_" + dt.datetime.now().strftime("%Y%m%d_%H%M%S"))
    backup_dir.mkdir(parents=True, exist_ok=False)
    shutil.copy2(MAIN, backup_dir / "main.py")
    shutil.copy2(AVATAR, backup_dir / "avatar.py")
    try:
        MAIN.write_text(next_main, encoding="utf-8")
        AVATAR.write_text(next_avatar, encoding="utf-8")
        # Final syntax check against actual written files; if it fails, restore immediately.
        ast.parse(MAIN.read_text(encoding="utf-8"), filename=str(MAIN))
        ast.parse(AVATAR.read_text(encoding="utf-8"), filename=str(AVATAR))
    except Exception:
        shutil.copy2(backup_dir / "main.py", MAIN)
        shutil.copy2(backup_dir / "avatar.py", AVATAR)
        raise

    print("[Capri v8] Установлено успешно.")
    print("Изменены только main.py и avatar.py.")
    print(f"Резервные копии: {backup_dir}")
    print("Перезапусти Капри. В меню правой кнопки появится «Оставаться на рабочем столе».")
    print("Состояние галочки сохраняется в config.json; при включении Капри не скрывается по таймеру.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
