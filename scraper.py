import os
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

        self._fallback_build_id = os.getenv("CRICHEROES_BUILD_ID", "8iMSuY1ejzbaFdLLYf6fm")
        self._cached_build_id = None

    def _discover_build_id(self, url=None):
        """Try to extract the Next.js buildId from a CricHeroes page."""
        urls_to_try = []
        if url:
            urls_to_try.append(url)
        urls_to_try.extend([
            f"{self.base_url}/",
            f"{self.base_url}/tournament",
        ])
        patterns = [r'"buildId":"(.*?)"', r'/_next/data/([^/"]+)/']
        for try_url in urls_to_try:
            try:
                response = self.session.get(try_url, timeout=6)
                if response.status_code == 200:
                    for pattern in patterns:
                        match = re.search(pattern, response.text)
                        if match:
                            return match.group(1)
            except Exception as e:
                print(f"DEBUG: Build ID discovery error for {try_url}: {e}")
        return None

    def _get_build_id(self, url=None, force_refresh=False):
        """Return a usable Next.js buildId. Caches in memory; refreshes on demand."""
        if not force_refresh and self._cached_build_id:
            return self._cached_build_id

        fresh = self._discover_build_id(url)
        if fresh:
            if fresh != self._cached_build_id:
                print(f"DEBUG: Build ID set to {fresh} (was {self._cached_build_id or self._fallback_build_id})")
            self._cached_build_id = fresh
            return fresh

        if not self._cached_build_id:
            print(f"DEBUG: Discovery failed; using env fallback {self._fallback_build_id}")
            self._cached_build_id = self._fallback_build_id
        return self._cached_build_id

    def invalidate_build_id(self):
        self._cached_build_id = None

    def _fetch_tab(self, build_id, tournament_id, slug, tab_path, params, is_direct_path=False, _retried=False):
        """Fetch JSON data from the internal Next.js endpoint. Auto-refreshes build id on 404."""
        if is_direct_path:
            url = f"{self.base_url}/_next/data/{build_id}/{tab_path}.json"
        else:
            url = f"{self.base_url}/_next/data/{build_id}/tournament/{tournament_id}/{slug}/{tab_path}.json"

        try:
            response = self.session.get(url, params=params, timeout=10)
            if response.status_code == 404 and not _retried:
                # build id likely rotated — invalidate and retry once
                print(f"DEBUG: 404 on {tab_path}; refreshing build id and retrying")
                self.invalidate_build_id()
                new_build_id = self._get_build_id(force_refresh=True)
                if new_build_id and new_build_id != build_id:
                    return self._fetch_tab(new_build_id, tournament_id, slug, tab_path, params, is_direct_path, _retried=True)
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

        # Live matches: CricHeroes 307-redirects /summary to /live, so the summary
        # tab response is just a redirect marker. Fetch /live and reshape its
        # miniScorecard.data into the same shape as past-match summaryData.data.
        summary_resp = results.get("summary") or {}
        if summary_resp.get("__N_REDIRECT"):
            live_path = f"scorecard/{match_id}/{tournament_slug}/{team_slug}/live"
            live_resp = self._fetch_tab(build_id, None, None, live_path, {**params, "tab": "live"}, is_direct_path=True)
            mini = (live_resp.get("miniScorecard") or {}).get("data")
            if not mini:
                # fallback: scorecard tab also carries miniScorecard for live matches
                mini = ((results.get("scorecard") or {}).get("miniScorecard") or {}).get("data")
            if mini:
                results["summary"] = {
                    "summaryData": {"status": True, "data": mini},
                    "scorecard": [],
                    "tab": "summary",
                }

        return {
            "success": True,
            "match_id": match_id,
            "details": results,
            "scraped_at": time.strftime("%Y-%m-%dT%H:%M:%SZ")
        }

    def scrape_live_matches(self, tournament_id, slug):
        """Lightweight: only fetch the live-matches tab. Used by the fast cron."""
        tournament_url = f"{self.base_url}/tournament/{tournament_id}/{slug}/matches/live-matches"
        build_id = self._get_build_id(tournament_url)
        if not build_id:
            return {"success": False, "error": "Could not find Build ID for tournament"}

        base_params = {"tournamentId": tournament_id, "tournamentName": slug}
        live_matches = self._fetch_tab(
            build_id, tournament_id, slug, 'matches/live-matches',
            {**base_params, "tabName": "matches", "innerTab": "live-matches"}
        )

        matches = (
            live_matches.get("matchResponse", {}).get("data", [])
            or live_matches.get("live_matches", [])
            or []
        )

        return {
            "success": True,
            "matches": matches,
            "scraped_at": time.strftime("%Y-%m-%dT%H:%M:%SZ"),
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

        squads_data = self._fetch_tab(build_id, tournament_id, slug, 'squads', 
                                     {**base_params, "tabName": "squads"})
        
        print(f"DEBUG: Squads Raw Keys: {list(squads_data.keys()) if squads_data else 'EMPTY'}")
        if squads_data and "squads" in squads_data:
             print(f"DEBUG: Squads Data Type: {type(squads_data['squads'])}")
             if isinstance(squads_data['squads'], dict):
                 print(f"DEBUG: Squads Dict Keys: {list(squads_data['squads'].keys())}")

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
            team_data = teams_data.get("tournamentDetails", {}).get("teams", [])
        
        # Merge squads info
        squad_teams = squads_data.get("squads", {}).get("data", [])
        if not squad_teams:
            squad_teams = squads_data.get("tournamentDetails", {}).get("squads", [])

        if squad_teams:
            squad_map = {str(st.get("team_id")): st.get("players", []) for st in squad_teams}
            for team in team_data:
                tid = str(team.get("team_id") or team.get("id"))
                if tid in squad_map and squad_map[tid]:
                    team["players"] = squad_map[tid]
        
        # Check if players are nested in team_data
        for team in team_data:
            if "players" not in team or not team["players"]:
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
