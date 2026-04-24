import requests
import re
import time

class CricHeroesScraper:
    def __init__(self):
        self.base_url = "https://cricheroes.com"
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
        })

    def _get_build_id(self, tournament_id, slug):
        """Fetch the main tournament page and extract the Next.js buildId."""
        url = f"{self.base_url}/tournament/{tournament_id}/{slug}/matches/past-matches"
        try:
            response = self.session.get(url, timeout=10)
            match = re.search(r'"buildId":"([^"]+)"', response.text)
            return match.group(1) if match else None
        except Exception as e:
            print(f"Error fetching Build ID: {e}")
            return None

    def _fetch_tab(self, build_id, tournament_id, slug, tab_path, params, is_direct_path=False):
        """Fetch JSON data from the internal Next.js endpoint."""
        if is_direct_path:
            url = f"{self.base_url}/_next/data/{build_id}/{tab_path}.json"
        else:
            url = f"{self.base_url}/_next/data/{build_id}/tournament/{tournament_id}/{slug}/{tab_path}.json"
            
        try:
            response = self.session.get(url, params=params, timeout=10)
            if response.status_code != 200:
                print(f"Failed to fetch {tab_path}: {response.status_code}")
                return {}
            return response.json().get("pageProps", {})
        except Exception as e:
            print(f"Error fetching tab {tab_path}: {e}")
            return {}

    def slugify(self, text):
        import re
        text = text.lower()
        text = re.sub(r'[^a-z0-9 ]', '', text)
        return text.replace(' ', '-')

    def scrape_match_details(self, match_id, tournament_slug, team_a, team_b):
        build_id = self._get_build_id(tournament_id="1499216", slug=tournament_slug)
        if not build_id:
            return {"success": False, "error": "Could not get build ID"}

        team_slug = f"{self.slugify(team_a)}-vs-{self.slugify(team_b)}"
        
        # Paths for different tabs
        paths = {
            "summary": f"scorecard/{match_id}/{tournament_slug}/{team_slug}/summary",
            "scorecard": f"scorecard/{match_id}/{tournament_slug}/{team_slug}/scorecard",
            "full-scorecard": f"scorecard/{match_id}/{tournament_slug}/{team_slug}/full-scorecard",
            "squads": f"scorecard/{match_id}/{tournament_slug}/{team_slug}/squads"
        }

        params = {
            "matchId": match_id,
            "tournamentName": tournament_slug,
            "teamNames": team_slug
        }

        results = {}
        for tab, path in paths.items():
            results[tab] = self._fetch_tab(build_id, None, None, path, {**params, "tab": tab}, is_direct_path=True)

        return {
            "success": True,
            "match_id": match_id,
            "details": results,
            "scraped_at": time.strftime("%Y-%m-%dT%H:%M:%SZ")
        }

    def scrape_all(self, tournament_id, slug):
        build_id = self._get_build_id(tournament_id, slug)
        if not build_id:
            return {"success": False, "error": "Could not find Build ID"}

        base_params = {"tournamentId": tournament_id, "tournamentName": slug}

        # Fetch tabs
        past_matches = self._fetch_tab(build_id, tournament_id, slug, 'matches/past-matches', 
                                      {**base_params, "tabName": "matches", "innerTab": "past-matches"})
        
        teams_data = self._fetch_tab(build_id, tournament_id, slug, 'teams', 
                                     {**base_params, "tabName": "teams"})

        points_table = self._fetch_tab(build_id, tournament_id, slug, 'points-table', 
                                      {**base_params, "tabName": "points-table"})
        
        leaderboard = self._fetch_tab(build_id, tournament_id, slug, 'leaderboard', 
                                     {**base_params, "tabName": "leaderboard"})

        # Map data to consistent structure
        match_data = past_matches.get("matchResponse", {}).get("data", [])
        if not match_data:
            match_data = past_matches.get("past_matches", [])
            
        team_data = teams_data.get("teamResponse", {}).get("data", [])
        if not team_data:
            team_data = past_matches.get("tournamentDetails", {}).get("teams", [])

        standing_data = points_table.get("teamStandings", {})
        if isinstance(standing_data, dict):
            standing_data = standing_data.get("data", [])
        
        print(f"Scrape Result: {len(match_data)} matches, {len(team_data)} teams, {len(standing_data)} standings")
        
        return {
            "success": True,
            "matches": match_data,
            "teams": team_data,
            "standings": standing_data,
            "leaderboard": leaderboard.get("leaderBoardTeams", {}).get("data", []),
            "scraped_at": time.strftime("%Y-%m-%dT%H:%M:%SZ")
        }
