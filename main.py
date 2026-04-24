import os
from datetime import datetime
from fastapi import FastAPI, Header, HTTPException, Depends
from dotenv import load_dotenv
from scraper import CricHeroesScraper

load_dotenv()

app = FastAPI(title="GPL Scraper Service")

SYNC_SECRET = os.getenv("ADMIN_TOKEN") or os.getenv("SYNC_SECRET")
scraper = CricHeroesScraper()

async def verify_secret(x_sync_secret: str = Header(None)):
    if x_sync_secret != SYNC_SECRET:
        raise HTTPException(status_code=401, detail="Invalid sync secret")

@app.get("/health")
def health():
    return {"status": "ok", "timestamp": datetime.utcnow().isoformat()}

@app.get("/scrape/{tournament_id}", dependencies=[Depends(verify_secret)])
def scrape_full(tournament_id: str, slug: str = "govindaplly-premier-leauge-2"):
    """
    Scrapes all data for a tournament.
    slug defaults to the provided GPL slug if not specified.
    """
    result = scraper.scrape_all(tournament_id, slug)
    if not result.get("success"):
        raise HTTPException(status_code=500, detail=result.get("error", "Scraping failed"))
    return result

@app.get("/scrape/match/{match_id}", dependencies=[Depends(verify_secret)])
def scrape_match(match_id: str, slug: str, team_a: str, team_b: str):
    """
    Scrapes detailed scorecard for a specific match.
    """
    result = scraper.scrape_match_details(match_id, slug, team_a, team_b)
    if not result.get("success"):
        raise HTTPException(status_code=500, detail=result.get("error", "Scraping failed"))
    return result

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
