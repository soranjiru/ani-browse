from dataclasses import dataclass


@dataclass(slots=True)
class Anime:
    id: int
    title: str
    score: float | None
    genres: list[str]
    episodes: int | None
    status: str
    season: str
    synopsis: str
    rank: int | None = None
    popularity: int | None = None
    members: int | None = None