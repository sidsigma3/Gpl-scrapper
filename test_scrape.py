import os
from scraper import CricHeroesScraper
from dotenv import load_dotenv

# Test URL ID provided by user
TEST_ID = "1499216"

def test_scrape():
    print(f"Testing scraper with ID: {TEST_ID}")
    scraper = CricHeroesScraper()
    
    try:
        data = scraper.scrape_all(TEST_ID)
        
        print("\n--- Scraping Results Summary ---")
        print(f"Matches: {len(data['matches'])}")
        print(f"Teams: {len(data['teams'])}")
        print(f"Players: {len(data['players'])}")
        print(f"Leaderboard: {data['leaderboard']}")
        
    except Exception as e:
        print(f"Error during scraping: {str(e)}")

if __name__ == "__main__":
    test_scrape()
