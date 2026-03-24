import json
import re
import subprocess
from difflib import SequenceMatcher

import httpx

from .models import Anime


ALLANIME_API = "https://api.allanime.day/api"
SEARCH_GQL = """
query($search: SearchInput, $limit: Int, $page: Int, $translationType: VaildTranslationTypeEnumType, $countryOrigin: VaildCountryOriginEnumType) {
  shows(search: $search, limit: $limit, page: $page, translationType: $translationType, countryOrigin: $countryOrigin) {
    edges {
      name
      availableEpisodes
    }
  }
}
""".strip()


def normalize_title(text: str) -> str:
    text = " ".join(text.split())
    text = text.replace("’", "'").replace("–", "-").replace("—", "-")
    return text


def normalize_for_match(text: str) -> str:
    text = normalize_title(text).lower()
    text = re.sub(r"[^\w\s]", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def similarity(a: str, b: str) -> float:
    return SequenceMatcher(None, a, b).ratio()


def build_play_query(anime: Anime) -> str:
    return normalize_title(anime.title)


def search_candidates(query: str, prefer_dub: bool = False) -> list[str]:
    mode = "dub" if prefer_dub else "sub"

    variables = {
        "search": {
            "allowAdult": False,
            "allowUnknown": False,
            "query": query.replace(" ", "+"),
        },
        "limit": 40,
        "page": 1,
        "translationType": mode,
        "countryOrigin": "ALL",
    }

    response = httpx.get(
        ALLANIME_API,
        params={
            "variables": json.dumps(variables, separators=(",", ":")),
            "query": SEARCH_GQL,
        },
        headers={"Referer": "https://allmanga.to"},
        timeout=15.0,
    )
    response.raise_for_status()

    edges = response.json().get("data", {}).get("shows", {}).get("edges", [])

    results: list[str] = []
    for edge in edges:
        title = str(edge.get("name") or "").strip()
        if not title:
            continue

        available = edge.get("availableEpisodes") or {}
        if available.get(mode) in (None, 0, "0"):
            continue

        results.append(title)

    return results


def choose_best_index(anime: Anime, candidates: list[str]) -> int | None:
    target = normalize_for_match(anime.title)

    best_index = None
    best_score = -1.0

    for i, title in enumerate(candidates, start=1):
        cand = normalize_for_match(title)

        if cand == target:
            return i

        score = similarity(target, cand)
        if score > best_score:
            best_score = score
            best_index = i

    if best_score >= 0.88:
        return best_index

    return None


def play_anime(anime: Anime, prefer_dub: bool = False, episode: int | None = None) -> int:
    query = build_play_query(anime)

    cmd = ["ani-cli"]
    if prefer_dub:
        cmd.append("--dub")

    if episode is not None:
        cmd.extend(["-e", str(episode)])

    try:
        candidates = search_candidates(query, prefer_dub=prefer_dub)
        index = choose_best_index(anime, candidates)
        if index is not None:
            cmd.extend(["-S", str(index)])
    except Exception:
        pass

    cmd.append(query)
    result = subprocess.run(cmd, check=False)
    return result.returncode