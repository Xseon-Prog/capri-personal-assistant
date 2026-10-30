#!/usr/bin/env python3
"""Add a persistent manual standby toggle to the Capri settings menu."""
from __future__ import annotations

import ast
import datetime as dt
import shutil
from pathlib import Path

MARKER = "CAPRI_MANUAL_STANDBY_V1"
HOLD_MARKER = "CAPRI_STANDBY_HOLD_V1_1"


def fail(message: str) -> None:
    print(f"[Capri Manual Standby v1] Ошибка: {message}")
    raise SystemExit(1)


def replace_once(source: str, old: str, new: str, label: str) -> str:
    count = source.count(old)
    if count != 1:
        fail(f"Совместимость не подтверждена: {label}; найдено {count} совпадений вместо 1. Файлы не изменены.")
    return source.replace(old, new, 1)


def main() -> int:
    root = Path(__file__).resolve().parent.parent
    main_path = root / "main.py"
    avatar_path = root / "avatar.py"
    if not main_path.is_file() or not avatar_path.is_file():
        fail("Не найдены main.py или avatar.py. Запусти установщик из папки tools проекта.")

    main_text = main_path.read_text(encoding="utf-8-sig")
    avatar_text = avatar_path.read_text(encoding="utf-8-sig")

    if MARKER in main_text or MARKER in avatar_text:
        fail("Постоянный переключатель режима ожидания уже установлен.")
    if "CAPRI_STANDBY_MODE_V1" not in main_text or HOLD_MARKER not in avatar_text:
        fail("Не найдена ожидаемая версия режима ожидания. Сначала установи Standby Mode v1 и исправление Hold v1.1.")

    patched_main = main_text
    patched_avatar = avatar_text

    # Persistent preference is stored in config.json, default off.
    patched_main = replace_once(
        patched_main,
        '    "standby_after_seconds": 20,  # CAPRI_STANDBY_MODE_V1: 20 / 40 / 60 / 0 (never)\n',
        '    "standby_after_seconds": 20,  # CAPRI_STANDBY_MODE_V1: 20 / 40 / 60 / 0 (never)\n'
        '    "manual_standby_enabled": False,  # CAPRI_MANUAL_STANDBY_V1\n',
        "параметр постоянного режима ожидания",
    )

    # Install a checkable menu action immediately above the automatic standby timer submenu.
    menu_insert = '''            manual_standby_act = QAction("Включить режим ожидания", settings_menu)
            manual_standby_act.setCheckable(True)
            manual_standby_act.setChecked(bool(capri.cfg.get("manual_standby_enabled", False)))

            def set_manual_standby(checked):
                enabled = bool(checked)
                capri.cfg["manual_standby_enabled"] = enabled
                save_setting("manual_standby_enabled", enabled)
                avatar.set_manual_standby(enabled)
                log.info("Постоянный режим ожидания: %s", "включён" if enabled else "выключен")

            manual_standby_act.toggled.connect(set_manual_standby)
            settings_menu.addAction(manual_standby_act)

'''
    patched_main = replace_once(
        patched_main,
        '            standby_menu = settings_menu.addMenu("Настройка режима ожидания")\n',
        menu_insert + '            standby_menu = settings_menu.addMenu("Настройка режима ожидания")\n',
        "переключатель над настройкой таймера ожидания",
    )

    # Sync checkbox every time Settings is opened.
    sync_anchor = '''                selected_standby = int(capri.cfg.get("standby_after_seconds", 20))
'''
    sync_replacement = '''                manual_standby_act.blockSignals(True)
                manual_standby_act.setChecked(bool(capri.cfg.get("manual_standby_enabled", False)))
                manual_standby_act.blockSignals(False)
                selected_standby = int(capri.cfg.get("standby_after_seconds", 20))
'''
    patched_main = replace_once(
        patched_main, sync_anchor, sync_replacement, "синхронизация переключателя режима ожидания"
    )

    # If persistent standby was enabled before exit, restore it on the next launch.
    startup_anchor = '''    if avatar.stay_visible:
        avatar.summon()
'''
    startup_replacement = '''    manual_standby_enabled = bool(cfg.get("manual_standby_enabled", False))
    if avatar.stay_visible or manual_standby_enabled:
        avatar.summon()
    if manual_standby_enabled:
        avatar.set_manual_standby(True)
'''
    patched_main = replace_once(
        patched_main, startup_anchor, startup_replacement, "восстановление постоянного режима при запуске"
    )

    # Add the separate manual flag to the avatar state.
    patched_avatar = replace_once(
        patched_avatar,
        '        self.standby_active = False\n        self.last_activity_monotonic = time.monotonic()\n',
        '        self.standby_active = False\n'
        '        self.manual_standby_enabled = False  # CAPRI_MANUAL_STANDBY_V1\n'
        '        self.last_activity_monotonic = time.monotonic()\n',
        "состояние постоянного режима ожидания",
    )

    # The existing activity signal is used for voice/text jobs. It must not unlock a manual standby.
    patched_avatar = replace_once(
        patched_avatar,
        '    def mark_activity(self):\n        """Reset the idle timer after a recognised Capri interaction (including voice)."""\n        self.last_activity_monotonic = time.monotonic()\n        if self.standby_active:\n            self._leave_standby()\n',
        '    def mark_activity(self):\n        """Reset the idle timer; a manually latched standby remains active."""\n        self.last_activity_monotonic = time.monotonic()\n        if self.manual_standby_enabled:  # CAPRI_MANUAL_STANDBY_V1\n            self._enforce_manual_standby()\n            return\n        if self.standby_active:\n            self._leave_standby()\n',
        "сохранение ручного режима при регистрации голосовой/текстовой активности",
    )

    # Explicitly enabled standby cannot be hidden via the normal automatic hide action.
    patched_avatar = replace_once(
        patched_avatar,
        '''    def vanish(self):
        self.standby_active = False
        if self.anim == "standby":
            self.anim = None
        if self.state in ("visible", "appearing"):
            self.state, self.k = "vanishing", 0
''',
        '''    def vanish(self):
        if self.manual_standby_enabled:  # CAPRI_MANUAL_STANDBY_V1: only the Settings toggle turns it off
            self._enforce_manual_standby()
            return
        self.standby_active = False
        if self.anim == "standby":
            self.anim = None
        if self.state in ("visible", "appearing"):
            self.state, self.k = "vanishing", 0
''',
        "защита постоянного ожидания от авто-скрытия",
    )

    # Keep the standby animation even when other app components request listening/thinking/speaking animations.
    patched_avatar = replace_once(
        patched_avatar,
        '''    def play_anim(self, name, loop=False):
        if name in self.anims:
''',
        '''    def play_anim(self, name, loop=False):
        if self.manual_standby_enabled and name != "standby":  # CAPRI_MANUAL_STANDBY_V1
            return
        if name in self.anims:
''',
        "приоритет анимации постоянного ожидания",
    )

    patched_avatar = replace_once(
        patched_avatar,
        '''    def set_mode(self, mode, seconds=0.0):
        if self.standby_active and mode != "standby":  # CAPRI_STANDBY_HOLD_V1_1
''',
        '''    def set_mode(self, mode, seconds=0.0):
        if self.manual_standby_enabled:  # CAPRI_MANUAL_STANDBY_V1: ignore transient modes while latched
            self._enforce_manual_standby()
            return
        if self.standby_active and mode != "standby":  # CAPRI_STANDBY_HOLD_V1_1
''',
        "сохранение постоянного режима при запросах и озвучивании",
    )

    # Insert public toggle and a helper before the existing automatic standby methods.
    standby_method_anchor = '''    def set_standby_after(self, seconds):
'''
    manual_methods = '''    def _enforce_manual_standby(self):
        """Keep the looping standby animation active until the Settings toggle is switched off."""
        if self.state == "hidden":
            self.summon()
        self.standby_active = True
        self.mode = "standby"
        self.mode_until = 0.0
        self.hide_at = 0.0
        self.hopping = False
        if self.anim != "standby":
            self.anim = None
            self.play_anim("standby", loop=True)
        self.update()

    def set_manual_standby(self, enabled):
        """Enable/disable persistent standby; while enabled it survives voice/text requests."""
        enabled = bool(enabled)
        self.manual_standby_enabled = enabled
        if enabled:
            self._enforce_manual_standby()
            return
        self.standby_active = False
        if self.anim == "standby":
            self.anim = None
        self.last_activity_monotonic = time.monotonic()
        self.last_standby_poll = 0.0
        self.set_mode("idle", 0.0)

'''
    patched_avatar = replace_once(
        patched_avatar, standby_method_anchor, manual_methods + standby_method_anchor,
        "метод включения/выключения постоянного режима ожидания",
    )

    # Ensure the automatic standby poll never changes a manually latched state.
    patched_avatar = replace_once(
        patched_avatar,
        '''    def _update_standby(self, now):
        if now - self.last_standby_poll < 0.5:
''',
        '''    def _update_standby(self, now):
        if self.manual_standby_enabled:  # CAPRI_MANUAL_STANDBY_V1
            self._enforce_manual_standby()
            return
        if now - self.last_standby_poll < 0.5:
''',
        "приоритет ручного режима над автоматическим таймером",
    )

    for name, content in (("main.py", patched_main), ("avatar.py", patched_avatar)):
        try:
            ast.parse(content)
            compile(content, name, "exec")
        except SyntaxError as exc:
            fail(f"Проверка синтаксиса {name} не пройдена: строка {exc.lineno}: {exc.msg}")

    stamp = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_dir = root / "backups" / f"capri_manual_standby_{stamp}"
    backup_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(main_path, backup_dir / "main.py")
    shutil.copy2(avatar_path, backup_dir / "avatar.py")

    main_path.write_text(patched_main, encoding="utf-8")
    avatar_path.write_text(patched_avatar, encoding="utf-8")

    print("[Capri Manual Standby v1] Постоянный режим ожидания установлен успешно.")
    print(f"[Capri Manual Standby v1] Резервная копия: {backup_dir}")
    print('[Capri Manual Standby v1] В настройках добавлен переключатель "Включить режим ожидания" над настройкой таймера.')
    print("[Capri Manual Standby v1] При включении анимация остаётся активной во время запросов и озвучивания.")
    print("[Capri Manual Standby v1] Режим сохраняется после перезапуска; выключается тем же переключателем в настройках.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
