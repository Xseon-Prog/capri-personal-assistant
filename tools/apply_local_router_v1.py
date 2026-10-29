"""Install the first local request router in an existing Capricorn checkout.

Copy router.py into the project root and this installer into tools/, then run:
    py -3.13 tools\\apply_local_router_v1.py

No cloud provider is added or enabled. Backups are created before writing.
"""
from __future__ import annotations

import ast
import datetime as dt
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / "main.py"
LOCAL_AI = ROOT / "local_ai.py"
ROUTER = ROOT / "router.py"
MARKER = "CAPRI_LOCAL_ROUTER_V1"


def replace_once(source: str, old: str, new: str, label: str) -> str:
    count = source.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: ожидалось одно совпадение, найдено {count}; файл не изменён.")
    return source.replace(old, new, 1)


def patch_main(source: str) -> str:
    if MARKER in source:
        return source
    if "CAPRI_MENU_PIN_V8" not in source:
        raise RuntimeError("Не найден маркер v8. Убедись, что текущие обновления Капри установлены.")

    source = replace_once(
        source,
        "    from local_ai import LocalAI\n",
        "    from local_ai import LocalAI\n    from router import RequestRouter  # " + MARKER + "\n",
        "импорт локального маршрутизатора",
    )
    source = replace_once(
        source,
        "        self.actions.local = self.local\n",
        "        self.actions.local = self.local\n"
        "        self.router = RequestRouter()  # " + MARKER + "\n",
        "инициализация маршрутизатора",
    )

    old = '''        reply = self.actions.handle(cmd)
        if reply is not None and reply.action in ("mic_info", "mic_next"):
            reply = self.mic_command(reply.action)
        if reply is None:
            if self.cfg.get("enable_ai") and self.ai.available:
                reply = Reply(self.ai.ask(cmd), "answer")
            else:
                answer = self.local.ask(cmd) if self.local else None
                reply = Reply(answer, "answer") if answer else self.actions.fallback(cmd, force_search=bool(self.local))
'''
    new = '''        reply = self.actions.handle(cmd)
        decision = None
        if reply is not None:
            log.info("Маршрут запроса: windows_tool — команда обработана существующим исполнителем")
        else:
            decision = self.router.classify(cmd)
            log.info("Маршрут запроса: %s — %s", decision.route, decision.reason)

        if reply is not None and reply.action in ("mic_info", "mic_next"):
            reply = self.mic_command(reply.action)
        if reply is None:
            if self.cfg.get("enable_ai") and self.ai.available:
                # Сохраняется только уже настроенная пользователем интеграция; маршрутизатор её не включает.
                reply = Reply(self.ai.ask(cmd), "answer")
            elif decision and decision.needs_search:
                reply = self.actions.fallback(cmd, force_search=True)
            else:
                answer = (self.local.ask(cmd, detailed=bool(decision and decision.detailed))
                          if self.local else None)
                if answer:
                    reply = Reply(answer, "answer")
                else:
                    log.info("Локальная модель не вернула ответ; используется существующий резервный сценарий")
                    reply = self.actions.fallback(cmd, force_search=bool(self.local))
'''
    source = replace_once(source, old, new, "диспетчеризация запросов")
    return source


def patch_local_ai(source: str) -> str:
    if MARKER in source:
        return source
    if "CAPRI_LOCAL_DIALOGUE_V5" not in source or "CAPRI_CYBERPUNK_UI_V7" not in source:
        raise RuntimeError("Не найдены маркеры локального диалога v5 и UI v7 в local_ai.py.")
    if "DETAIL_REQUEST_RE" not in source:
        raise RuntimeError("В local_ai.py не найден обработчик подробных запросов.")

    source = replace_once(
        source,
        "    def ask(self, question):\n",
        "    def ask(self, question, detailed=False):  # " + MARKER + "\n",
        "поддержка признака подробного маршрута",
    )
    occurrences = source.count("if DETAIL_REQUEST_RE.search(question):")
    if occurrences != 1:
        raise RuntimeError(f"правила контекста: ожидалось одно условие детализации, найдено {occurrences}.")
    source = replace_once(
        source,
        "if DETAIL_REQUEST_RE.search(question):",
        "if detailed or DETAIL_REQUEST_RE.search(question):",
        "расширенные инструкции для сложного запроса",
    )
    source = replace_once(
        source,
        "max_tokens = 1200 if DETAIL_REQUEST_RE.search(question) else 420",
        "max_tokens = 1200 if (detailed or DETAIL_REQUEST_RE.search(question)) else 420  # " + MARKER,
        "лимит генерации для сложного запроса",
    )
    return source


def main() -> int:
    missing = [p.name for p in (MAIN, LOCAL_AI, ROUTER) if not p.is_file()]
    if missing:
        print("[Capri Router v1] Не найдены файлы: " + ", ".join(missing))
        print("Скопируй router.py в корень проекта, а установщик — в tools/.")
        return 1

    try:
        main_src = MAIN.read_text(encoding="utf-8-sig")
        ai_src = LOCAL_AI.read_text(encoding="utf-8-sig")
        patched_main = patch_main(main_src)
        patched_ai = patch_local_ai(ai_src)
        router_src = ROUTER.read_text(encoding="utf-8-sig")
        ast.parse(patched_main, filename=str(MAIN))
        ast.parse(patched_ai, filename=str(LOCAL_AI))
        ast.parse(router_src, filename=str(ROUTER))
    except Exception as exc:
        print(f"[Capri Router v1] Проверка не пройдена: {exc}")
        print("Файлы не изменены. Пришли это сообщение для проверки совместимости.")
        return 1

    changes = {MAIN: patched_main, LOCAL_AI: patched_ai}
    changes = {p: content for p, content in changes.items() if content != p.read_text(encoding="utf-8-sig")}
    if not changes:
        print("[Capri Router v1] Маршрутизатор уже установлен; изменений не требуется.")
        return 0

    backup = ROOT / "backups" / ("capri_local_router_v1_" + dt.datetime.now().strftime("%Y%m%d_%H%M%S"))
    try:
        backup.mkdir(parents=True, exist_ok=False)
        for path in changes:
            shutil.copy2(path, backup / path.name)
        written = []
        try:
            for path, content in changes.items():
                path.write_text(content, encoding="utf-8")
                written.append(path)
            for path in changes:
                ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        except Exception:
            for path in written:
                shutil.copy2(backup / path.name, path)
            raise
    except Exception as exc:
        print(f"[Capri Router v1] Не удалось применить обновление: {exc}")
        return 1

    print("[Capri Router v1] Обновление установлено успешно.")
    print("Изменены: main.py, local_ai.py. Новый модуль: router.py.")
    print(f"Резервные копии: {backup}")
    print("Маршруты: Windows-команда / локальный разговор / сложный локальный запрос / актуальный поиск.")
    print("Облачные провайдеры этим обновлением не подключаются и не включаются.")
    print("Полностью выйди из Капри через системный трей и запусти run.bat.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
