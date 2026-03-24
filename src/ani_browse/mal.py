import os
import json
import time
from dataclasses import dataclass
from pathlib import Path

import httpx
from dotenv import load_dotenv

from .models import Anime

load_dotenv()

BASE_URL = "https://api.myanimelist.net/v2"

CACHE_DIR = Path.home() / ".cache" / "ani-browse"
CACHE_DIR.mkdir(parents=True, exist_ok=True)

CACHE_TTL_SECONDS = 60 * 60 * 12  # 12 hours

CONFIG_DIR = Path.home() / ".config" / "ani-browse"
APP_CONFIG_PATH = CONFIG_DIR / "config.json"

def load_app_config() -> dict:
    if not APP_CONFIG_PATH.exists():
        return {}

    try:
        return json.loads(APP_CONFIG_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}


def save_app_config(data: dict) -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    APP_CONFIG_PATH.write_text(
        json.dumps(data, indent=2),
        encoding="utf-8",
    )


def get_saved_client_id() -> str | None:
    config = load_app_config()
    client_id = config.get("mal_client_id")
    if isinstance(client_id, str) and client_id.strip():
        return client_id.strip()
    return None

def validate_client_id(client_id: str) -> bool:
    headers = {"X-MAL-CLIENT-ID": client_id}
    try:
        response = httpx.get(
            f"{BASE_URL}/anime/ranking",
            headers=headers,
            params={"ranking_type": "all", "limit": 1},
            timeout=10.0,
        )
        response.raise_for_status()
        return True
    except Exception:
        return False

@dataclass
class AnimePage:
    items: list[Anime]
    has_next: bool
    has_previous: bool


_memory_cache: dict[str, AnimePage] = {}

def _cache_path(key: str) -> Path:
    safe_key = key.replace("/", "_").replace(":", "_").replace(" ", "_")
    return CACHE_DIR / f"{safe_key}.json"


def _anime_to_dict(anime: Anime) -> dict:
    return {
        "id": anime.id,
        "title": anime.title,
        "score": anime.score,
        "genres": anime.genres,
        "episodes": anime.episodes,
        "status": anime.status,
        "season": anime.season,
        "synopsis": anime.synopsis,
        "rank": anime.rank,
        "popularity": anime.popularity,
        "members": anime.members,
    }


def _anime_from_dict(data: dict) -> Anime:
    return Anime(
        id=data["id"],
        title=data["title"],
        score=data["score"],
        genres=data["genres"],
        episodes=data["episodes"],
        status=data["status"],
        season=data["season"],
        synopsis=data["synopsis"],
        rank=data.get("rank"),
        popularity=data.get("popularity"),
        members=data.get("members"),
    )


def _load_from_cache(key: str) -> AnimePage | None:
    if key in _memory_cache:
        return _memory_cache[key]

    path = _cache_path(key)
    if not path.exists():
        return None

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None

    timestamp = payload.get("timestamp")
    if not isinstance(timestamp, (int, float)):
        return None

    if time.time() - timestamp > CACHE_TTL_SECONDS:
        return None

    items = [_anime_from_dict(item) for item in payload.get("items", [])]
    page = AnimePage(
        items=items,
        has_next=payload.get("has_next", False),
        has_previous=payload.get("has_previous", False),
    )
    _memory_cache[key] = page
    return page


def _save_to_cache(key: str, page: AnimePage) -> None:
    _memory_cache[key] = page

    payload = {
        "timestamp": time.time(),
        "items": [_anime_to_dict(anime) for anime in page.items],
        "has_next": page.has_next,
        "has_previous": page.has_previous,
    }

    _cache_path(key).write_text(
        json.dumps(payload, ensure_ascii=False),
        encoding="utf-8",
    )

def clear_cache() -> None:
    _memory_cache.clear()

    for path in CACHE_DIR.glob("*.json"):
        path.unlink(missing_ok=True)


def clear_cache_key(key: str) -> None:
    _memory_cache.pop(key, None)
    _cache_path(key).unlink(missing_ok=True)


def make_seasonal_cache_key(year: int, season: str, limit: int, offset: int) -> str:
    return f"seasonal:{year}:{season}:{limit}:{offset}"


def make_search_cache_key(query: str, limit: int, offset: int) -> str:
    normalized_query = query.strip().lower()
    return f"search:{normalized_query}:{limit}:{offset}"


def make_ranking_cache_key(ranking_type: str, limit: int, offset: int) -> str:
    return f"ranking:{ranking_type}:{limit}:{offset}"

def has_client_id() -> bool:
    try:
        return bool(get_client_id())
    except Exception:
        return False

def get_client_id() -> str:
    env_client_id = os.getenv("MAL_CLIENT_ID")
    if env_client_id and env_client_id.strip():
        return env_client_id.strip()

    saved_client_id = get_saved_client_id()
    if saved_client_id:
        return saved_client_id

    raise RuntimeError("MAL_CLIENT_ID is not set")


def _parse_page(payload: dict) -> tuple[bool, bool]:
    paging = payload.get("paging", {}) or {}
    has_next = bool(paging.get("next"))
    has_previous = bool(paging.get("previous"))
    return has_next, has_previous


def parse_anime(node: dict) -> Anime:
    title = node.get("title", "Unknown Title")
    score = node.get("mean")
    episodes = node.get("num_episodes")
    synopsis = node.get("synopsis") or "No synopsis available."

    genres = [genre["name"] for genre in node.get("genres", [])]

    start_season = node.get("start_season")
    if start_season:
        season_name = start_season.get("season", "")
        season_year = start_season.get("year", "")
        season = f"{season_name.capitalize()} {season_year}".strip()
    else:
        season = "Unknown"

    status = node.get("status", "unknown").replace("_", " ").title()

    return Anime(
        id=node["id"],
        title=title,
        score=score,
        genres=genres,
        episodes=episodes,
        status=status,
        season=season,
        synopsis=synopsis,
        rank=node.get("rank"),
        popularity=node.get("popularity"),
        members=node.get("num_list_users"),
    )

def search_anime(query: str, limit: int = 50, offset: int = 0) -> AnimePage:
    cache_key = make_search_cache_key(query, limit, offset)
    cached = _load_from_cache(cache_key)
    if cached is not None:
        return cached

    headers = {"X-MAL-CLIENT-ID": get_client_id()}
    params = {
        "q": query,
        "limit": limit,
        "offset": offset,
        "fields": "id,title,mean,num_episodes,synopsis,genres,start_season,status,rank,popularity,num_list_users",
    }

    response = httpx.get(f"{BASE_URL}/anime", headers=headers, params=params, timeout=15.0)
    response.raise_for_status()

    payload = response.json()
    items = [parse_anime(item["node"]) for item in payload.get("data", [])]
    has_next, has_previous = _parse_page(payload)

    page = AnimePage(items=items, has_next=has_next, has_previous=has_previous)
    _save_to_cache(cache_key, page)
    return page


def get_seasonal_anime(year: int, season: str, limit: int = 50, offset: int = 0) -> AnimePage:
    cache_key = make_seasonal_cache_key(year, season, limit, offset)
    cached = _load_from_cache(cache_key)
    if cached is not None:
        return cached

    headers = {"X-MAL-CLIENT-ID": get_client_id()}
    params = {
        "limit": limit,
        "offset": offset,
        "fields": "id,title,mean,num_episodes,synopsis,genres,start_season,status,rank,popularity,num_list_users",
    }

    response = httpx.get(
        f"{BASE_URL}/anime/season/{year}/{season}",
        headers=headers,
        params=params,
        timeout=15.0,
    )
    response.raise_for_status()

    payload = response.json()
    items = [parse_anime(item["node"]) for item in payload.get("data", [])]
    has_next, has_previous = _parse_page(payload)

    page = AnimePage(items=items, has_next=has_next, has_previous=has_previous)
    _save_to_cache(cache_key, page)
    return page


def get_ranking_anime(ranking_type: str, limit: int = 50, offset: int = 0) -> AnimePage:
    cache_key = make_ranking_cache_key(ranking_type, limit, offset)
    cached = _load_from_cache(cache_key)
    if cached is not None:
        return cached

    headers = {"X-MAL-CLIENT-ID": get_client_id()}
    params = {
        "ranking_type": ranking_type,
        "limit": limit,
        "offset": offset,
        "fields": "id,title,mean,num_episodes,synopsis,genres,start_season,status,rank,popularity,num_list_users",
    }

    response = httpx.get(f"{BASE_URL}/anime/ranking", headers=headers, params=params, timeout=15.0)
    response.raise_for_status()

    payload = response.json()
    items = [parse_anime(item["node"]) for item in payload.get("data", [])]
    has_next, has_previous = _parse_page(payload)

    page = AnimePage(items=items, has_next=has_next, has_previous=has_previous)
    _save_to_cache(cache_key, page)
    return page