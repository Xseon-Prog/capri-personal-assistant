"""Install Capri provider interface v1 into an existing Capricorn checkout.

Safe behavior: validates expected source anchors and syntax before writing,
creates a backup, and keeps all provider calls local by default.
"""
from __future__ import annotations

import datetime
import os
from pathlib import Path
import py_compile
import shutil
import sys
import tempfile

BASE = Path(__file__).resolve().parents[1]
MARKER = "CAPRI_PROVIDER_HUB_V1"


def fail(message: str) -> int:
    print(f"[Capri Provider Hub v1] ОШИБКА: {message}")
    print("Файлы проекта не изменены, если не указано обратное.")
    return 1


def replace_once(source: str, old: str, new: str, label: str) -> str:
    count = source.count(old)
    if count != 1:
        raise ValueError(f"Не удалось однозначно найти участок '{label}' (совпадений: {count}).")
    return source.replace(old, new, 1)


def main() -> int:
    if not (BASE / "main.py").is_file() or not (BASE / "local_ai.py").is_file():
        return fail("запусти установщик из папки tools существующего проекта Capricorn.")
    if not (BASE / "router.py").is_file():
        return fail("не найден router.py. Сначала установи и проверь Router v1.")

    paths = {name: BASE / name for name in ("main.py", "local_ai.py", "actions.py", ".gitignore")}
    try:
        original = {name: path.read_text(encoding="utf-8-sig") for name, path in paths.items()}
    except OSError as exc:
        return fail(f"не удалось прочитать исходные файлы: {exc}")

    if all(MARKER in original[name] for name in ("main.py", "local_ai.py", "actions.py")):
        print("[Capri Provider Hub v1] Обновление уже установлено; повторное изменение не требуется.")
        return 0
    if any(MARKER in original[name] for name in ("main.py", "local_ai.py", "actions.py")):
        return fail("обнаружена частичная установка маркеров; восстанови согласованную резервную копию перед повтором.")

    main_py = original["main.py"]
    local_py = original["local_ai.py"]
    actions_py = original["actions.py"]
    gitignore = original[".gitignore"]

    try:
        main_py = replace_once(
            main_py,
            "    from router import RequestRouter  # CAPRI_LOCAL_ROUTER_V1\n",
            "    from router import RequestRouter  # CAPRI_LOCAL_ROUTER_V1\n    from provider_hub import ProviderHub  # CAPRI_PROVIDER_HUB_V1\n",
            "импорт RequestRouter",
        )
        main_py = replace_once(
            main_py,
            '    "local_ai": True,\n    "local_model": "qwen3:8b",\n',
            '    "local_ai": True,\n    "local_model": "qwen3:8b",\n    "provider_mode": "local",  # CAPRI_PROVIDER_HUB_V1\n    "provider_usage_logging": True,\n',
            "значения по умолчанию",
        )
        main_py = replace_once(
            main_py,
            '        self.router = RequestRouter()  # CAPRI_LOCAL_ROUTER_V1\n',
            '        self.router = RequestRouter()  # CAPRI_LOCAL_ROUTER_V1\n'
            '        self.provider_hub = ProviderHub(cfg, self.local)  # CAPRI_PROVIDER_HUB_V1\n',
            "инициализация маршрутизатора",
        )
        old_route_block = '''        if reply is None:
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
        new_route_block = '''        if reply is None:
            if decision and decision.needs_search:
                reply = self.actions.fallback(cmd, force_search=True)
            else:
                route_name = decision.route if decision else "local_chat"
                result = self.provider_hub.ask(
                    cmd,
                    detailed=bool(decision and decision.detailed),
                    route=route_name,
                )
                answer = result.text if result else None
                if result:
                    log.info(
                        "Ответ провайдера: %s/%s; input_tokens=%s output_tokens=%s cost_usd=%.8f",
                        result.provider, result.model, result.input_tokens, result.output_tokens, result.cost_usd,
                    )
                if answer:
                    reply = Reply(answer, "answer")
                else:
                    log.info("Локальная модель не вернула ответ; используется существующий резервный сценарий")
                    reply = self.actions.fallback(cmd, force_search=bool(self.local))
'''
        main_py = replace_once(main_py, old_route_block, new_route_block, "маршрут ответа локальной модели")

        local_py = replace_once(
            local_py,
            '        self.model = cfg.get("local_model", "qwen3:8b")  # CAPRI_LOCAL_DIALOGUE_V2\n        self.history = []\n',
            '        self.model = cfg.get("local_model", "qwen3:8b")  # CAPRI_LOCAL_DIALOGUE_V2\n'
            '        self.last_usage = None  # CAPRI_PROVIDER_HUB_V1: токены последнего запроса Ollama\n'
            '        self.history = []\n',
            "инициализация LocalAI",
        )
        local_py = replace_once(
            local_py,
            '        text = strip_reasoning(resp.get("message", {}).get("content", ""))\n',
            '        self.last_usage = {  # CAPRI_PROVIDER_HUB_V1\n'
            '            "model": str(resp.get("model") or self.model),\n'
            '            "input_tokens": resp.get("prompt_eval_count"),\n'
            '            "output_tokens": resp.get("eval_count"),\n'
            '        }\n'
            '        text = strip_reasoning(resp.get("message", {}).get("content", ""))\n',
            "счётчики токенов из ответа Ollama",
        )
        local_py = replace_once(
            local_py,
            '        if FRESH.search(question.lower()):\n            return None\n',
            '        self.last_usage = None  # CAPRI_PROVIDER_HUB_V1: не использовать счётчики прошлого запроса\n'
            '        if FRESH.search(question.lower()):\n            return None\n',
            "сброс счётчиков перед запросом",
        )
        actions_py = replace_once(
            actions_py,
            '        use_ai = self.cfg.get("enable_ai") and self.ai and self.ai.available\n',
            '        use_ai = False  # CAPRI_PROVIDER_HUB_V1: облачные вызовы отложены до отдельного этапа\n',
            "облачный вызов в сводке диагностики",
        )
        if "usage.jsonl" not in gitignore:
            gitignore = gitignore.rstrip() + "\n\n# Local provider usage statistics (never commit)\nusage.jsonl\n"

        # Compile candidates before touching the user's working files.
        compile_dir = Path(tempfile.mkdtemp(prefix="capri_provider_hub_check_"))
        candidates = {
            "main.py": main_py,
            "local_ai.py": local_py,
            "actions.py": actions_py,
            ".gitignore": gitignore,
        }
        for name, content in candidates.items():
            temp_path = compile_dir / (name.replace(".", "_") + ".py")
            temp_path.write_text(content, encoding="utf-8")
            if name.endswith(".py"):
                py_compile.compile(str(temp_path), doraise=True)
        shutil.rmtree(compile_dir, ignore_errors=True)
    except Exception as exc:
        return fail(str(exc))

    backup_dir = BASE / "backups" / ("capri_provider_hub_v1_" + datetime.datetime.now().strftime("%Y%m%d_%H%M%S"))
    try:
        backup_dir.mkdir(parents=True, exist_ok=False)
        for name, path in paths.items():
            shutil.copy2(path, backup_dir / name.replace("/", "__"))
        for name, content in candidates.items():
            paths[name].write_text(content, encoding="utf-8", newline="\n")
        # Validate the saved form too.
        for name in ("main.py", "local_ai.py", "actions.py"):
            py_compile.compile(str(paths[name]), doraise=True)
    except Exception as exc:
        for name, path in paths.items():
            saved = backup_dir / name.replace("/", "__")
            if saved.exists():
                shutil.copy2(saved, path)
        return fail(f"запись не удалась; выполнен откат из {backup_dir}: {exc}")

    print("[Capri Provider Hub v1] Обновление установлено успешно.")
    print("[Capri Provider Hub v1] Активный режим: local (Ollama). Облачные запросы не выполняются.")
    print(f"[Capri Provider Hub v1] Резервная копия: {backup_dir}")
    print("[Capri Provider Hub v1] Статистика: %LOCALAPPDATA%\\Capri\\usage.jsonl; вопросы и ответы в журнал не записываются.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
