import requests
import re
import time
from bs4 import BeautifulSoup

class CricHeroesScraper:
    def __init__(self):
        import random
        self.base_url = "https://cricheroes.com"
        self.session = requests.Session()
        
        user_agents = [
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Mozilla/5.0 (iPhone; CPU iPhone OS 17_1 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.1 Mobile/15E148 Safari/604.1"
        ]
        
        self.session.headers.update({
            "User-Agent": random.choice(user_agents),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
        })

    def _get_build_id(self, url):
        """Fetch the page at the given URL and extract the Next.js buildId."""
        # Hardcoded Build ID provided by user to bypass Cloudflare discovery issues
        provided_build_id = "VJCa1OqVcXtUf3QXmrsKn"
        
        try:
            # Try discovery first (as it might have changed or be different for other pages)
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
            }
            response = self.session.get(url, headers=headers, timeout=5)
            if response.status_code == 200:
                patterns = [r'"buildId":"(.*?)"', r'\/_next\/data\/(.*?)\/']
                for pattern in patterns:
                    match = re.search(pattern, response.text)
                    if match:
                        return match.group(1)
            
            # If discovery fails (e.g. Cloudflare block), use the provided one
            print(f"DEBUG: Discovery failed/blocked. Using provided Build ID: {provided_build_id}")
            return provided_build_id
        except Exception as e:
            print(f"DEBUG: Build ID Discovery Error: {str(e)}. Falling back to {provided_build_id}")
            return provided_build_id

    def _fetch_tab(self, build_id, tournament_id, slug, tab_path, params, is_direct_path=False):
        """Fetch JSON data from the internal Next.js endpoint."""
        if is_direct_path:
            url = f"{self.base_url}/_next/data/{build_id}/{tab_path}.json"
        else:
            url = f"{self.base_url}/_next/data/{build_id}/tournament/{tournament_id}/{slug}/{tab_path}.json"
            
        try:
            response = self.session.get(url, params=params, timeout=10)
            if response.status_code != 200:
                print(f"DEBUG: Failed to fetch {tab_path}: {response.status_code}")
                return {}
            return response.json().get("pageProps", {})
        except Exception as e:
            print(f"DEBUG: Error fetching tab {tab_path}: {e}")
            return {}

    def slugify(self, text):
        text = str(text).lower()
        text = re.sub(r'[^a-z0-9 ]', '', text)
        return text.replace(' ', '-')

    def scrape_match_details(self, match_id, tournament_slug, team_a, team_b):
        team_slug = f"{self.slugify(team_a)}-vs-{self.slugify(team_b)}"
        match_url = f"{self.base_url}/scorecard/{match_id}/{tournament_slug}/{team_slug}/summary"
        
        build_id = self._get_build_id(match_url)
        if not build_id:
            # Try a generic slug if the specific one fails
            match_url = f"{self.base_url}/scorecard/{match_id}/match-details/summary"
            build_id = self._get_build_id(match_url)
            if not build_id:
                return {"success": False, "error": "Could not get build ID from match page"}
        
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
        tournament_url = f"{self.base_url}/tournament/{tournament_id}/{slug}/matches/past-matches"
        build_id = self._get_build_id(tournament_url)
        if not build_id:
            return {"success": False, "error": "Could not find Build ID for tournament"}

        base_params = {"tournamentId": tournament_id, "tournamentName": slug}

        # Fetch tabs
        past_matches = self._fetch_tab(build_id, tournament_id, slug, 'matches/past-matches', 
                                      {**base_params, "tabName": "matches", "innerTab": "past-matches"})
        
        upcoming_matches = self._fetch_tab(build_id, tournament_id, slug, 'matches/upcoming-matches', 
                                          {**base_params, "tabName": "matches", "innerTab": "upcoming-matches"})
        
        live_matches = self._fetch_tab(build_id, tournament_id, slug, 'matches/live-matches', 
                                      {**base_params, "tabName": "matches", "innerTab": "live-matches"})
        
        teams_data = self._fetch_tab(build_id, tournament_id, slug, 'teams', 
                                     {**base_params, "tabName": "teams"})

        points_table = self._fetch_tab(build_id, tournament_id, slug, 'points-table', 
                                      {**base_params, "tabName": "points-table"})
        print(f"DEBUG: Points Table Raw Keys: {list(points_table.keys()) if points_table else 'EMPTY'}")
        
        leaderboard = self._fetch_tab(build_id, tournament_id, slug, 'leaderboard', 
                                     {**base_params, "tabName": "leaderboard"})

        # Map data to consistent structure
        all_matches = []
        
        # Helper to extract matches from response
        def extract_matches(data_resp):
            resp = data_resp.get("matchResponse", {}).get("data", [])
            if not resp:
                resp = data_resp.get("past_matches", [])
            if not resp:
                resp = data_resp.get("upcoming_matches", [])
            if not resp:
                resp = data_resp.get("live_matches", [])
            return resp

        all_matches.extend(extract_matches(past_matches))
        all_matches.extend(extract_matches(upcoming_matches))
        all_matches.extend(extract_matches(live_matches))
        
        match_data = all_matches
            
        team_data = teams_data.get("teamResponse", {}).get("data", [])
        if not team_data:
            # Fallback for different JSON structures
            team_data = teams_data.get("tournamentDetails", {}).get("teams", [])
        
        # Check if players are nested in team_data
        for team in team_data:
            if "players" not in team or not team["players"]:
                # If not present, we could fetch them, but user says they are in teams.json
                # We'll just log if they are missing
                pass

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
