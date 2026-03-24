from dataclasses import dataclass, field


@dataclass(slots=True)
class Anime:
    id: int
    title: str
    score: float | None
    genres: list[str] = field(default_factory=list)
    episodes: int | None = None
    status: str = "Unknown"
    season: str = "Unknown"
    synopsis: str = "Fetching Synopsis..."
    rank: int | None = None
    popularity: int | None = None
    members: int | None = None

    list_title: str = ""
    list_subtitle: str = ""
    details_text: str = ""

    def finalize_display_fields(self) -> None:
        score = f"{self.score:.1f}" if self.score is not None else "N/A"
        episodes = self.episodes if self.episodes is not None else "N/A"
        genres = ", ".join(self.genres) if self.genres else "N/A"

        self.list_title = f"#{self.rank} {self.title}" if self.rank is not None else self.title
        self.list_subtitle = f"{score} • {self.season or self.status}"

        self.details_text = (
            f"[b]{self.title}[/b]\n"
            f"{'─' * len(self.title)}\n\n"
            f"[b]Score:[/b] {score}\n"
            f"[b]Episodes:[/b] {episodes}\n"
            f"[b]Status:[/b] {self.status}\n"
            f"[b]Season:[/b] {self.season}\n"
            f"[b]Genres:[/b] {genres}\n\n"
            f"[b]Synopsis[/b]\n"
            f"{self.synopsis}"
        )