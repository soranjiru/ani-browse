from textual.app import App, ComposeResult
from textual.containers import Horizontal, Container
from textual.widgets import Header, Footer, ListView, ListItem, Static, Input
from textual.binding import Binding
from textual import work

from .models import Anime
from .player import play_anime
from .mal import (
    get_seasonal_anime,
    search_anime,
    get_ranking_anime,
    get_anime_details,
    clear_cache_key,
    make_seasonal_cache_key,
    make_search_cache_key,
    make_ranking_cache_key,
    AnimePage,
    has_client_id,
    load_app_config,
    save_app_config,
    validate_client_id,
)

from datetime import date
import json
from pathlib import Path
import webbrowser

# class AnimeListRow(Static):
#     def __init__(self, anime: Anime) -> None:
#         self.anime = anime

#         score = f"{anime.score:.1f}" if anime.score is not None else "N/A"
#         secondary = anime.season if anime.season else anime.status
#         title = f"#{anime.rank} {anime.title}" if anime.rank is not None else anime.title

#         text = f"[b]{title}[/b]\n[dim]{score} • {secondary}[/dim]"
#         super().__init__(text, classes="anime-row")

class AnimeListRow(Static):
    def __init__(self, anime: Anime) -> None:
        self.anime = anime
        text = f"[b]{anime.list_title}[/b]\n[dim]{anime.list_subtitle}[/dim]"
        super().__init__(text, classes="anime-row")


class SeasonListRow(Static):
    def __init__(self, year: int, season: str) -> None:
        super().__init__(f"{year} {season.capitalize()}", classes="season-row")
        self.year = year
        self.season = season


# class AnimeDetails(Static):
#     def show_anime(self, anime: Anime) -> None:
#         score = f"{anime.score:.1f}" if anime.score is not None else "N/A"
#         episodes = anime.episodes if anime.episodes is not None else "N/A"
#         genres = ", ".join(anime.genres) if anime.genres else "N/A"

#         self.update(
#             f"[b]{anime.title}[/b]\n"
#             f"{'─' * len(anime.title)}\n\n"
#             f"[b]Score:[/b] {score}\n"
#             f"[b]Episodes:[/b] {episodes}\n"
#             f"[b]Status:[/b] {anime.status}\n"
#             f"[b]Season:[/b] {anime.season}\n"
#             f"[b]Genres:[/b] {genres}\n\n"
#             f"[b]Synopsis[/b]\n"
#             f"{anime.synopsis}"
#         )
class AnimeDetails(Static):
    def show_anime(self, anime: Anime) -> None:
        self.update(anime.details_text)

class StatusBar(Static):
    def set_content(self, text: str) -> None:
        self.update(text)


class AniBrowseApp(App):
    CSS = """
        Screen {
            layout: vertical;
            background: $surface;
        }

        Header {
            dock: top;
        }

        Footer {
            dock: bottom;
        }

        #search-bar {
            height: 3;
            margin: 1 1 0 1;
            padding: 0 1;
            border: round $primary;
        }

        #search {
            height: 1;
            border: none;
            background: transparent;
        }

        #status-bar {
            height: 1;
            padding: 0 1;
            margin: 0 1;
            color: $text-muted;
        }

        #main {
            height: 1fr;
            margin: 0 1 1 1;
        }

        #anime-list {
            width: 38%;
            border: round white;
        }

        #details {
            width: 62%;
            border: round white;
            padding: 1 2;
        }

        .anime-list-item {
            height: auto;
            min-height: 2;
            padding: 0 1;
        }

        .anime-row {
            height: auto;
        }

        .season-list-item {
            height: 1;
            padding: 0 1;
        }

        .season-row {
            text-style: bold;
            color: $text;
        }
    """

    BINDINGS = [
        Binding("/", "focus_search", "Search"),
        Binding("escape", "unfocus_search", "Back", show=False),
        Binding("s", "switch_view('seasonal')", "Seasonal"),
        Binding("t", "switch_view('top')", "Top"),
        Binding("p", "switch_view('popular')", "Popular"),
        Binding("u", "switch_view('upcoming')", "Upcoming"),
        Binding("d", "toggle_dub", "Dub"),
        Binding("comma", "previous_page", "Prev Page", show=False),
        Binding("full_stop", "next_page", "Next Page", show=False),
        Binding("ctrl+s", "show_season_picker", "Seasons"),
        Binding("[", "previous_season", "", show=False),
        Binding("]", "next_season", "", show=False),
        Binding("r", "refresh_view", "Refresh"),
        Binding("ctrl+o", "open_mal_page", "Open In MAL"),
        Binding("q", "quit", "Quit"),
    ]

    CONFIG_PATH = Path.home() / ".config" / "ani-browse" / "settings.json"

    def load_settings(self) -> dict:
        if not self.CONFIG_PATH.exists():
            return {}

        try:
            return json.loads(self.CONFIG_PATH.read_text(encoding="utf-8"))
        except Exception:
            return {}


    def save_settings(self) -> None:
        self.CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)

        data = {
            "season_year": self.season_year,
            "season_name": self.season_name,
            "season_options": self.season_options,
            "theme": getattr(self, "theme", None),
            "current_view": self.current_view,
            "last_search_query": self.last_search_query,
            "prefer_dub": self.prefer_dub,
            "page_size": self.page_size,
            "current_page": self.current_page,
        }

        self.CONFIG_PATH.write_text(
            json.dumps(data, indent=2),
            encoding="utf-8",
        )
    
    @property
    def current_offset(self) -> int:
        return self.current_page * self.page_size
    
    def update_chrome(self) -> None:
        page_text = f"Page {self.current_page + 1}"

        if self.current_view == "seasonal":
            main = f"ani-browse | Seasonal: {self.season_name.capitalize()} {self.season_year} ({page_text})"

            season_actions: list[str] = []
            if not self.is_oldest_season():
                season_actions.append("[ Prev Season")
            if not self.is_latest_season():
                season_actions.append("] Next Season")

            actions = "  ".join(f"[ {action} ]" for action in season_actions)
        elif self.current_view == "top":
            main = f"ani-browse | Top Anime ({page_text})"
            actions = ""
        elif self.current_view == "popular":
            main = f"ani-browse | Popular Anime ({page_text})"
            actions = ""
        elif self.current_view == "upcoming":
            main = f"ani-browse | Upcoming Anime ({page_text})"
            actions = ""
        elif self.current_view == "search":
            main = f"ani-browse | Search: {self.last_search_query} ({page_text})"
            actions = ""
        else:
            main = f"ani-browse | {self.current_view.capitalize()} ({page_text})"
            actions = ""

        page_actions = []
        if self.has_previous_page:
            page_actions.append("[ < Prev Page ]")
        if self.has_next_page:
            page_actions.append("[ > Next Page ]")

        parts = [main]
        if actions:
            parts.append(actions)
        parts.extend(page_actions)

        self.query_one("#status-bar", StatusBar).set_content("  ".join(parts))

    @work(exclusive=True, thread=True)
    def load_anime_details_async(self, anime_id: int, list_index: int) -> None:
        try:
            anime = get_anime_details(anime_id)
            self.call_from_thread(self._finish_load_anime_details, anime, list_index)
        except Exception as e:
            self.call_from_thread(self.notify, f"Failed to load details: {e}", severity="error")

    def _finish_load_anime_details(self, anime: Anime, list_index: int) -> None:
        if list_index >= len(self.current_anime_list):
            return

        if self.current_anime_list[list_index].id != anime.id:
            return

        self.current_anime_list[list_index] = anime

        list_view = self.query_one("#anime-list", ListView)
        if list_view.index == list_index:
            self.query_one("#details", AnimeDetails).show_anime(anime)

    @work(thread=True)
    def prefetch_page(
        self,
        view_name: str,
        page_number: int,
        season_year: int | None = None,
        season_name: str | None = None,
        search_query: str | None = None,
    ) -> None:
        offset = page_number * self.page_size

        try:
            if view_name == "seasonal" and season_year is not None and season_name is not None:
                get_seasonal_anime(
                    season_year,
                    season_name,
                    limit=self.page_size,
                    offset=offset,
                )
            elif view_name == "popular":
                get_ranking_anime("bypopularity", limit=self.page_size, offset=offset)
            elif view_name == "upcoming":
                get_ranking_anime("upcoming", limit=self.page_size, offset=offset)
            elif view_name == "top":
                get_ranking_anime("all", limit=self.page_size, offset=offset)
            elif view_name == "search" and search_query:
                search_anime(search_query, limit=self.page_size, offset=offset)
        except Exception:
            pass

    @work(exclusive=True, thread=True)
    def load_view_async(self, view_name: str, selected_title: str | None = None) -> None:

        try:
            if view_name == "seasonal":
                page = get_seasonal_anime(
                    self.season_year,
                    self.season_name,
                    limit=self.page_size,
                    offset=self.current_offset,
                )
                anime_list = page.items

            elif view_name == "popular":
                page = get_ranking_anime(
                    "bypopularity",
                    limit=self.page_size,
                    offset=self.current_offset,
                )
                anime_list = page.items

            elif view_name == "upcoming":
                page = get_ranking_anime(
                    "upcoming",
                    limit=self.page_size,
                    offset=self.current_offset,
                )
                anime_list = page.items

            elif view_name == "top":
                page = get_ranking_anime(
                    "all",
                    limit=self.page_size,
                    offset=self.current_offset,
                )
                anime_list = page.items

            elif view_name == "search":
                page = search_anime(
                    self.last_search_query,
                    limit=self.page_size,
                    offset=self.current_offset,
                )
                anime_list = page.items

            else:
                page = AnimePage(items=[], has_next=False, has_previous=False)
                anime_list = []

            self.call_from_thread(
                self._finish_load_view,
                view_name,
                anime_list,
                page.has_next,
                page.has_previous,
                selected_title,
            )

        except Exception as e:
            self.call_from_thread(self._handle_load_error, view_name, str(e))


    @work(thread=True)
    def refresh_season_options_async(self) -> None:
        season_options = self.build_season_options(
            years_back=20,
            max_future_seasons=4,
        )
        self.call_from_thread(self._finish_refresh_season_options, season_options)

    def _finish_refresh_season_options(
        self,
        season_options: list[tuple[int, str]],
    ) -> None:
        self.season_options = season_options
        self.save_settings()
        self.update_chrome()

    def _finish_load_view(
        self,
        view_name: str,
        anime_list: list[Anime],
        has_next: bool,
        has_previous: bool,
        selected_title: str | None = None,
    ) -> None:
        self.current_anime_list = anime_list
        self.has_next_page = has_next
        self.has_previous_page = has_previous

        self.populate_anime_list(selected_title=selected_title)
        self.update_chrome()
        if has_next:
            self.prefetch_page(
                view_name,
                self.current_page + 1,
                season_year=self.season_year,
                season_name=self.season_name,
                search_query=self.last_search_query,
            )


    def _handle_load_error(self, view_name: str, message: str) -> None:
        self.current_anime_list = []
        self.query_one("#details", AnimeDetails).update(
            f"[b]Error[/b]\n\nFailed to load {view_name} anime."
        )
        self.notify(message, severity="error")

    def action_toggle_dub(self) -> None:
        self.prefer_dub = not self.prefer_dub
        mode = "Dub" if self.prefer_dub else "Sub"
        self.notify(f"Audio: {mode}")
        self.save_settings()

    def get_current_season(self) -> tuple[int, str]:
        today = date.today()
        year = today.year
        month = today.month
        day = today.day

        if (month, day) >= (3, 21) and (month, day) < (6, 21):
            season = "spring"
        elif (month, day) >= (6, 21) and (month, day) < (9, 23):
            season = "summer"
        elif (month, day) >= (9, 23) and (month, day) < (12, 21):
            season = "fall"
        else:
            season = "winter"

        return year, season
        
    def get_current_season_index(self) -> int | None:
        target = (self.season_year, self.season_name)
        try:
            return self.season_options.index(target)
        except ValueError:
            return None


    def is_latest_season(self) -> bool:
        index = self.get_current_season_index()
        return index == 0


    def is_oldest_season(self) -> bool:
        index = self.get_current_season_index()
        return index == len(self.season_options) - 1 if index is not None else False

    def show_first_run_setup(self) -> None:
        self.list_mode = "setup"

        search = self.query_one("#search", Input)
        list_view = self.query_one("#anime-list", ListView)
        details = self.query_one("#details", AnimeDetails)

        search.placeholder = "Paste your MyAnimeList Client ID and press Enter..."
        search.value = ""

        list_view.clear()
        details.update(
            "[b]First Run Setup[/b]\n\n"
            "ani-browse needs a MyAnimeList API Client ID.\n\n"
            "[b]How to get one[/b]\n"
            "1. Open: [u]https://myanimelist.net/apiconfig[/u]\n"
            "2. Click [b]Create ID[/b]\n"
            "3. Fill out the form like this:\n\n"
            "   [b]App Name:[/b] ani-browse\n"
            "   [b]App Type:[/b] Other\n"
            "   [b]Description:[/b] Personal terminal anime browser\n"
            "   [b]Homepage URL:[/b] http://localhost\n"
            "   [b]App Redirect URL:[/b] http://localhost\n"
            "   [b]Commercial / Non-Commercial:[/b] Non-Commercial\n"
            "   [b]Name / Company Name:[/b] Your name\n"
            "   [b]Purpose of Use:[/b] Hobbyist / Personal use\n\n"
            "4. Submit the form\n"
            "5. Open the created app and copy the [b]Client ID[/b]\n"
            "6. Paste the Client ID into the box above and press Enter\n\n"
            "[dim]Only the Client ID is needed for ani-browse.[/dim]\n"
            "[dim]It will be saved to ~/.config/ani-browse/config.json[/dim]"
        )

        self.query_one("#status-bar", StatusBar).set_content("ani-browse | First Run Setup")
        search.focus()

    def handle_first_run_setup_submit(self, client_id: str) -> None:
        self.query_one("#details", AnimeDetails).update("[b]Validating API key...[/b]")

        if not validate_client_id(client_id):
            self.query_one("#details", AnimeDetails).update(
                "[b]First Run Setup[/b]\n\n"
                "That Client ID did not work.\n\n"
                "Please check that you copied the [b]Client ID[/b], not the client secret.\n"
                "You can find it on your app page at:\n"
                "[u]https://myanimelist.net/apiconfig[/u]\n\n"
                "Then paste it into the box above and press Enter."
            )
            self.notify("Invalid MyAnimeList Client ID", severity="error")
            return

        config = load_app_config()
        config["mal_client_id"] = client_id.strip()
        save_app_config(config)

        self.is_first_run_setup = False

        search = self.query_one("#search", Input)
        search.placeholder = "Search anime..."
        search.value = ""

        self.notify("MyAnimeList Client ID saved")
        self.query_one("#anime-list", ListView).focus()

        if not self.season_options:
            self.season_options = self.build_season_options_fast()

        self.load_view(self.current_view)
        # self.refresh_season_options_async()

    def __init__(self) -> None:
        super().__init__()

        settings = self.load_settings()
        default_year, default_season = self.get_current_season()

        self.current_view = settings.get("current_view", "top")
        self.last_search_query = settings.get("last_search_query", "")
        self.season_year = settings.get("season_year", default_year)
        self.season_name = settings.get("season_name", default_season)

        self.current_anime_list: list[Anime] = []
        self.season_options: list[tuple[int, str]] = []
        self.list_mode = "anime"
        self.prefer_dub = settings.get("prefer_dub", False)

        self.page_size = settings.get("page_size", 50)
        self.current_page = settings.get("current_page", 0)
        self.has_next_page = False
        self.has_previous_page = False

        raw_season_options = settings.get("season_options", [])
        self.season_options: list[tuple[int, str]] = []

        for item in raw_season_options:
            if isinstance(item, list) and len(item) == 2:
                year, season = item
                try:
                    self.season_options.append((int(year), str(season)))
                except Exception:
                    pass

        saved_theme = settings.get("theme")
        if saved_theme:
            self.theme = saved_theme

        self.is_first_run_setup = not has_client_id()

    def compose(self) -> ComposeResult:
        yield Header(show_clock=False)

        with Container(id="search-bar"):
            yield Input(placeholder="Search anime...", id="search")

        yield StatusBar(id="status-bar")

        with Horizontal(id="main"):
            yield ListView(id="anime-list")
            yield AnimeDetails(id="details")

        yield Footer()

    def on_mount(self) -> None:
        self.query_one("#anime-list", ListView).border_title = " Anime "
        self.query_one("#details", AnimeDetails).border_title = " Details "
        self.query_one("#search-bar", Container).border_title = " Search "

        if self.is_first_run_setup:
            self.show_first_run_setup()
            return

        if not self.season_options:
            self.season_options = self.build_season_options_fast()

        self.load_view(self.current_view)
        self.query_one("#anime-list", ListView).focus()

    def on_unmount(self) -> None:
        self.save_settings()

    def load_view(self, view_name: str, selected_title: str | None = None) -> None:
        self.current_view = view_name
        self.list_mode = "anime"
        self.has_next_page = False
        self.has_previous_page = self.current_page > 0

        self.query_one("#details", AnimeDetails).update("[b]Loading...[/b]")
        self.update_chrome()

        self.load_view_async(view_name, selected_title)

    def action_focus_search(self) -> None:
        self.query_one("#search", Input).focus()

    def action_unfocus_search(self) -> None:
        self.query_one("#anime-list", ListView).focus()


    def build_season_options(
        self,
        years_back: int = 20,
        max_future_seasons: int = 4,
    ) -> list[tuple[int, str]]:
        current_year, current_season = self.get_current_season()

        options: list[tuple[int, str]] = []

        year, season = current_year, current_season
        options.append((year, season))

        for _ in range(years_back * 4):
            year, season = self.get_previous_season_tuple(year, season)
            options.append((year, season))

        year, season = current_year, current_season
        future: list[tuple[int, str]] = []

        for _ in range(max_future_seasons):
            year, season = self.get_next_season_tuple(year, season)

            if not self.season_exists(year, season):
                break

            future.append((year, season))

        return future + options
    
    def build_season_options_fast(
        self,
        years_back: int = 20,
        future_seasons: int = 2,
    ) -> list[tuple[int, str]]:
        current_year, current_season = self.get_current_season()

        options: list[tuple[int, str]] = [(current_year, current_season)]

        year, season = current_year, current_season
        for _ in range(years_back * 4):
            year, season = self.get_previous_season_tuple(year, season)
            options.append((year, season))

        year, season = current_year, current_season
        future: list[tuple[int, str]] = []
        for _ in range(future_seasons):
            year, season = self.get_next_season_tuple(year, season)
            future.append((year, season))

        return future + options
    
    def action_show_season_picker(self) -> None:
        self.list_mode = "season_picker"

        list_view = self.query_one("#anime-list", ListView)
        details = self.query_one("#details", AnimeDetails)

        list_view.clear()

        for year, season in self.season_options:
            list_view.append(
                ListItem(
                    SeasonListRow(year, season),
                    classes="season-list-item",
                )
            )

        current_target = (self.season_year, self.season_name)
        if current_target in self.season_options:
            list_view.index = self.season_options.index(current_target)
        else:
            list_view.index = 0

        details.update(
            "[b]Season Picker[/b]\n\n"
            "Select a season and press Enter to load it."
        )

        self.query_one("#status-bar", StatusBar).set_content("ani-browse | Season Picker")
        list_view.focus()

    def action_previous_season(self) -> None:
        if self.current_view != "seasonal":
            return

        index = self.get_current_season_index()
        if index is None:
            return

        next_index = index + 1
        if next_index >= len(self.season_options):
            self.notify("Already on the oldest available season")
            return

        year, season = self.season_options[next_index]
        self.season_year = year
        self.season_name = season
        self.current_page = 0
        self.load_view("seasonal")
        self.save_settings()


    def action_next_season(self) -> None:
        if self.current_view != "seasonal":
            return

        index = self.get_current_season_index()
        if index is None:
            return

        next_index = index - 1
        if next_index < 0:
            self.notify("Already on the latest available season")
            return

        year, season = self.season_options[next_index]
        self.season_year = year
        self.season_name = season
        self.current_page = 0
        self.load_view("seasonal")
        self.save_settings()

    def get_next_season_tuple(self, year: int, season: str) -> tuple[int, str]:
        seasons = ["winter", "spring", "summer", "fall"]
        index = seasons.index(season)

        if index == len(seasons) - 1:
            return year + 1, "winter"

        return year, seasons[index + 1]


    def get_previous_season_tuple(self, year: int, season: str) -> tuple[int, str]:
        seasons = ["winter", "spring", "summer", "fall"]
        index = seasons.index(season)

        if index == 0:
            return year - 1, "fall"

        return year, seasons[index - 1]
    
    def season_exists(self, year: int, season: str) -> bool:
        try:
            page = get_seasonal_anime(year, season, limit=1, offset=0)
            return len(page.items) > 0
        except Exception:
            return False


    def action_next_page(self) -> None:
        if not self.has_next_page:
            self.notify("No next page")
            return

        self.current_page += 1
        self.load_view(self.current_view)
        self.save_settings()

    def action_previous_page(self) -> None:
        if self.current_page == 0:
            self.notify("Already on first page")
            return

        self.current_page -= 1
        self.load_view(self.current_view)
        self.save_settings()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        value = event.value.strip()
        if not value:
            return

        if self.is_first_run_setup:
            self.handle_first_run_setup_submit(value)
            return

        self.last_search_query = value
        self.current_page = 0
        self.current_view = "search"
        self.list_mode = "anime"

        self.query_one("#details", AnimeDetails).update("[b]Searching...[/b]")
        self.query_one("#search", Input).value = ""

        self.load_view("search")
        self.save_settings()

    def action_switch_view(self, view_name: str) -> None:
        self.current_page = 0
        self.load_view(view_name)
        self.save_settings()


    def on_list_view_selected(self, event: ListView.Selected) -> None:
        if event.list_view.index is None:
            return

        if self.list_mode == "season_picker":
            year, season = self.season_options[event.list_view.index]
            self.season_year = year
            self.season_name = season
            self.current_page = 0
            self.list_mode = "anime"
            self.load_view("seasonal")
            self.save_settings()
        else:
            self.action_play_selected()


    def action_play_selected(self) -> None:
        list_view = self.query_one("#anime-list", ListView)
        if list_view.index is None:
            return
        if not self.current_anime_list:
            return

        anime = self.current_anime_list[list_view.index]

        try:
            with self.suspend():
                return_code = play_anime(anime.title, prefer_dub=self.prefer_dub)

            list_view.focus()

            if return_code == 0:
                self.notify(f"Finished: {anime.title}")
            elif return_code in (1, 2, 130):
                self.notify("Playback cancelled")
            else:
                self.notify(f"Playback exited with code {return_code}", severity="warning")

        except FileNotFoundError:
            self.notify("ani-cli is not installed or not in PATH", severity="error")
        except Exception as e:
            self.notify(f"Playback failed: {e}", severity="error")


    def on_list_view_highlighted(self, event: ListView.Highlighted) -> None:
        if event.list_view.index is None:
            return

        if self.list_mode == "season_picker":
            year, season = self.season_options[event.list_view.index]
            self.query_one("#details", AnimeDetails).update(
                f"[b]{year} {season.capitalize()}[/b]\n\n"
                "Press Enter to load this seasonal anime list."
            )
            return

        if not self.current_anime_list:
            return

        index = event.list_view.index
        anime = self.current_anime_list[index]

        self.query_one("#details", AnimeDetails).show_anime(anime)

        needs_detail_fetch = (
            anime.episodes is None
            or not anime.genres
            or anime.synopsis == "No synopsis available."
        )

        if needs_detail_fetch:
            self.query_one("#details", AnimeDetails).update("[b]Loading details...[/b]")
            self.load_anime_details_async(anime.id, index)

    def action_refresh_view(self) -> None:
        if self.current_view == "seasonal":
            cache_key = make_seasonal_cache_key(
                self.season_year,
                self.season_name,
                self.page_size,
                self.current_offset,
            )
            clear_cache_key(cache_key)
            self.load_view("seasonal")
            self.notify(f"Refreshed {self.season_name.capitalize()} {self.season_year}")

        elif self.current_view == "popular":
            cache_key = make_ranking_cache_key(
                "bypopularity",
                self.page_size,
                self.current_offset,
            )
            clear_cache_key(cache_key)
            self.load_view("popular")
            self.notify("Refreshed popular anime")

        elif self.current_view == "upcoming":
            cache_key = make_ranking_cache_key(
                "upcoming",
                self.page_size,
                self.current_offset,
            )
            clear_cache_key(cache_key)
            self.load_view("upcoming")
            self.notify("Refreshed upcoming anime")

        elif self.current_view == "top":
            cache_key = make_ranking_cache_key(
                "all",
                self.page_size,
                self.current_offset,
            )
            clear_cache_key(cache_key)
            self.load_view("top")
            self.notify("Refreshed top anime")

        elif self.current_view == "search" and self.last_search_query:
            cache_key = make_search_cache_key(
                self.last_search_query,
                self.page_size,
                self.current_offset,
            )
            clear_cache_key(cache_key)
            self.load_view("search")
            self.notify(f"Refreshed search: {self.last_search_query}")


    def populate_anime_list(self, selected_title: str | None = None) -> None:
        list_view = self.query_one("#anime-list", ListView)
        details = self.query_one("#details", AnimeDetails)

        list_view.clear()

        selected_index = 0

        for index, anime in enumerate(self.current_anime_list):
            list_view.append(ListItem(AnimeListRow(anime), classes="anime-list-item"))
            if selected_title is not None and anime.title == selected_title:
                selected_index = index

        if self.current_anime_list:
            list_view.index = selected_index
            details.show_anime(self.current_anime_list[selected_index])
        else:
            details.update("No anime found.")

        list_view.focus()

    def action_open_mal_page(self) -> None:
        list_view = self.query_one("#anime-list", ListView)
        if list_view.index is None or not self.current_anime_list:
            return

        anime = self.current_anime_list[list_view.index]
        if getattr(anime, "id", None) is None:
            return

        webbrowser.open(f"https://myanimelist.net/anime/{anime.id}")

def main() -> None:
    AniBrowseApp().run()


if __name__ == "__main__":
    main()