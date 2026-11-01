"""Provider abstraction for Capri.

Current stage: local Ollama only. No cloud provider is registered or called.
Future provider adapters should implement generate() and return ProviderResponse
with usage metadata from the provider's API response.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
import json
import logging
import os
from pathlib import Path
import threading
from typing import Protocol

log = logging.getLogger("capri")
MARKER = "CAPRI_PROVIDER_HUB_V1"


def default_usage_path() -> Path:
    """Keep telemetry outside the project and away from Git commits."""
    root = os.environ.get("LOCALAPPDATA") or os.environ.get("APPDATA")
    if root:
        return Path(root) / "Capri" / "usage.jsonl"
    return Path.home() / ".capri" / "usage.jsonl"


@dataclass(frozen=True)
class ProviderResponse:
    """Normalized response shape shared by every provider adapter.

    Token counts should be the exact values returned by a provider when available.
    cost_usd is zero for local inference; a future cloud adapter must supply a
    cost computed from its actual usage and the selected model's current rates.
    """
    text: str | None
    provider: str
    model: str
    input_tokens: int | None = None
    output_tokens: int | None = None
    cost_usd: float = 0.0
    cost_is_estimate: bool = False


class TextProvider(Protocol):
    """Interface future cloud adapters must implement without exposing UI code."""
    name: str

    def generate(self, prompt: str, *, detailed: bool, route: str) -> ProviderResponse: ...


def calculate_cost_usd(
    input_tokens: int,
    output_tokens: int,
    input_usd_per_million: float,
    output_usd_per_million: float,
) -> float:
    """Calculate API cost from explicit per-million-token prices."""
    values = (input_tokens, output_tokens, input_usd_per_million, output_usd_per_million)
    if any(value < 0 for value in values):
        raise ValueError("Token counts and prices must be non-negative")
    return (input_tokens * input_usd_per_million + output_tokens * output_usd_per_million) / 1_000_000


class UsageLedger:
    """Append-only local usage ledger. It stores metrics, never prompts or responses."""
    def __init__(self, path: str | os.PathLike[str] | None = None):
        self.path = Path(path) if path is not None else default_usage_path()
        self._lock = threading.Lock()

    def record(self, result: ProviderResponse, route: str) -> None:
        record = {
            "timestamp_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "provider": result.provider,
            "model": result.model,
            "route": route,
            "input_tokens": result.input_tokens,
            "output_tokens": result.output_tokens,
            "cost_usd": round(max(0.0, float(result.cost_usd)), 8),
            "cost_is_estimate": bool(result.cost_is_estimate),
        }
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self._lock, self.path.open("a", encoding="utf-8", newline="\n") as handle:
                handle.write(json.dumps(record, ensure_ascii=False) + "\n")
        except OSError:
            log.exception("Не удалось записать локальную статистику использования провайдера")

    def summary(self) -> dict[str, int | float]:
        """Return aggregate usage without exposing the content of any conversation."""
        requests = input_tokens = output_tokens = 0
        cost_usd = 0.0
        try:
            with self.path.open("r", encoding="utf-8") as handle:
                for line in handle:
                    try:
                        item = json.loads(line)
                    except (ValueError, TypeError):
                        continue
                    requests += 1
                    input_tokens += int(item.get("input_tokens") or 0)
                    output_tokens += int(item.get("output_tokens") or 0)
                    cost_usd += float(item.get("cost_usd") or 0.0)
        except FileNotFoundError:
            pass
        except OSError:
            log.exception("Не удалось прочитать статистику использования провайдера")
        return {
            "requests": requests,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "total_tokens": input_tokens + output_tokens,
            "cost_usd": round(cost_usd, 8),
        }


class OllamaProvider:
    """Adapter for the existing LocalAI (Ollama) implementation."""
    name = "ollama"

    def __init__(self, local_ai):
        self.local_ai = local_ai

    def generate(self, prompt: str, *, detailed: bool, route: str) -> ProviderResponse:
        if self.local_ai is None:
            return ProviderResponse(None, self.name, "unavailable")
        text = self.local_ai.ask(prompt, detailed=detailed)
        usage = getattr(self.local_ai, "last_usage", None) or {}
        return ProviderResponse(
            text=text,
            provider=self.name,
            model=str(usage.get("model") or getattr(self.local_ai, "model", "unknown")),
            input_tokens=usage.get("input_tokens"),
            output_tokens=usage.get("output_tokens"),
            cost_usd=0.0,
            cost_is_estimate=False,
        )


class ProviderHub:
    """Selects a registered adapter. Only local Ollama is registered in this stage."""
    def __init__(self, cfg: dict, local_ai, ledger: UsageLedger | None = None):
        self.cfg = cfg
        self.ledger = ledger or UsageLedger()
        self.providers: dict[str, TextProvider] = {}
        if local_ai is not None:
            self.providers["local"] = OllamaProvider(local_ai)

    def register_provider(self, mode: str, provider: TextProvider) -> None:
        """Extension point for later adapters; this package registers no cloud adapters."""
        normalized = (mode or "").strip().lower()
        if not normalized or normalized == "local":
            raise ValueError("'local' is reserved for the Ollama adapter")
        self.providers[normalized] = provider

    def available_modes(self) -> tuple[str, ...]:
        return tuple(sorted(self.providers))

    def ask(self, prompt: str, *, detailed: bool = False, route: str = "local_chat") -> ProviderResponse | None:
        # Local is the enforced default for this stage. Setting a future provider name
        # does not make a network call: it must have an explicitly registered adapter.
        mode = str(self.cfg.get("provider_mode", "local") or "local").strip().lower()
        provider = self.providers.get(mode)
        if provider is None:
            log.warning("Провайдер '%s' не зарегистрирован; облачный запрос не выполнялся", mode)
            return None
        try:
            result = provider.generate(prompt, detailed=detailed, route=route)
        except Exception:
            log.exception("Ошибка провайдера '%s'", mode)
            return None
        if self.cfg.get("provider_usage_logging", True):
            self.ledger.record(result, route)
        return result

    def usage_summary(self) -> dict[str, int | float]:
        return self.ledger.summary()
