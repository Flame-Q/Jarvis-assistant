"""Web and YouTube search through the default browser."""

from __future__ import annotations

import re
import urllib.parse
import webbrowser

from pydantic import BaseModel

from jarvis.core.models import SkillResult
from jarvis.skills.base import BaseSkill, normalize_text


class SearchArgs(BaseModel):
    query: str = ""
    youtube: bool = False


class SearchWebSkill(BaseSkill):
    name = "search_web"
    description = "Найти информацию в интернете или на YouTube."
    examples = ["найди в интернете погоду на завтра", "включи на ютубе джаз"]
    triggers = ["найди", "загугли", "поиск", "ютубе", "youtube", "ютуб"]
    args_model: type[BaseModel] = SearchArgs

    def extract_args(self, text: str) -> SearchArgs:
        normalized = normalize_text(text)
        youtube = any(word in normalized for word in ("ютуб", "youtube"))
        query = normalized
        for phrase in (
            "найди в интернете",
            "поищи в интернете",
            "включи на ютубе",
            "найди на ютубе",
            "на ютубе",
            "в ютубе",
            "ютубе",
            "youtube",
            "найди",
            "загугли",
            "поиск",
        ):
            query = re.sub(rf"\b{re.escape(phrase)}\b", " ", query)
        return SearchArgs(query=" ".join(query.split()), youtube=youtube)

    def execute(self, args: BaseModel) -> SkillResult:
        assert isinstance(args, SearchArgs)
        if not args.query:
            return SkillResult.failure("Что именно найти?")
        encoded = urllib.parse.quote_plus(args.query)
        if args.youtube:
            webbrowser.open(f"https://www.youtube.com/results?search_query={encoded}")
            return SkillResult.success(f"Ищу на YouTube: {args.query}.")
        webbrowser.open(f"https://www.google.com/search?q={encoded}")
        return SkillResult.success(f"Ищу в интернете: {args.query}.")
