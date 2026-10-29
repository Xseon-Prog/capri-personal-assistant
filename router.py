"""Local, rule-based request router for Capricorn.

This module never calls a remote service or a language model. It only classifies
unknown requests after the existing Actions command handler has had first refusal.
"""
from __future__ import annotations

from dataclasses import dataclass
import re


ROUTER_MARKER = "CAPRI_LOCAL_ROUTER_V1"


@dataclass(frozen=True)
class RouteDecision:
    route: str
    reason: str
    detailed: bool = False
    needs_search: bool = False
    cloud_candidate: bool = False


_FRESH_PATTERNS = tuple(re.compile(p, re.IGNORECASE) for p in (
    r"\bкакая\s+погод\w*\b",
    r"\bпрогноз\s+погод\w*\b",
    r"\b(?:последние|свежие|актуальные|сегодняшние)\s+новост\w*\b",
    r"\bновост\w*\s+(?:сегодня|сейчас|за\s+сегодня|последние)\b",
    r"\bкурс\s+(?:доллар\w*|евро|валют\w*|биткоин\w*)(?:\s+(?:сегодня|сейчас|на\s+сегодня))?\b",
    r"\b(?:сколько\s+стоит|актуальная\s+цена|цена\s+сейчас|цены\s+сегодня)\b",
    r"\b(?:кто\s+выиграл|результат\s+матча|сч[её]т\s+матча)\b",
    r"\b(?:расписание|пробки)\b",
    r"\b(?:сейчас|сегодня|завтра|на\s+данный\s+момент)\b.{0,60}\b(?:курс|цен\w*|погод\w*|новост\w*|результат|расписан\w*|пробк\w*)\b",
))

_COMPLEX_PATTERNS = tuple(re.compile(p, re.IGNORECASE) for p in (
    r"\bподробн\w*\b",
    r"\bпо\s+шагам\b|\bпошагов\w*\b",
    r"\bразбер\w*\b|\bпроанализ\w*\b|\bисследуй\b",
    r"\bобъясн\w*\b|\bпоясн\w*\b",
    r"\bсравн\w*\b|\bразница\s+между\b|\bчем\b.{1,100}\bотлича\w*\b",
    r"\bсоставь\s+план\b|\bплан\s+действий\b|\bспланируй\b",
    r"\b(?:ошибк\w*|отлад\w*|исправ\w*)\b.{0,100}\b(?:код\w*|скрипт\w*|программ\w*)\b",
    r"\b(?:код\w*|скрипт\w*|проект\w*|архитектур\w*)\b",
    r"\bплюсы\s+и\s+минусы\b|\bнескольк\w*\s+файл\w*\b",
    r"\bпочему\b.{0,100}\b(?:ошибк\w*|не\s+работа\w*|сбой\w*)\b",
))


class RequestRouter:
    """Choose a local handling path without invoking another LLM."""

    def classify(self, text: str) -> RouteDecision:
        query = re.sub(r"\s+", " ", (text or "")).strip()
        if not query:
            return RouteDecision("local_chat", "пустой или нераспознанный запрос")

        for pattern in _FRESH_PATTERNS:
            if pattern.search(query):
                return RouteDecision(
                    "fresh_search",
                    "вероятно нужны актуальные сведения; используем существующий поиск",
                    needs_search=True,
                )

        complex_match = next((p for p in _COMPLEX_PATTERNS if p.search(query)), None)
        long_multistep = len(query) >= 220 or bool(re.search(r"\b(?:затем|после этого|а также)\b", query, re.I))
        if complex_match or long_multistep:
            reason = "многошаговый или развёрнутый запрос" if long_multistep else "запрос требует объяснения или анализа"
            return RouteDecision(
                "local_complex",
                reason + "; пока обрабатывается локальной моделью",
                detailed=True,
                cloud_candidate=True,
            )

        return RouteDecision(
            "local_chat",
            "обычный разговор или вопрос; используется локальная модель",
        )
