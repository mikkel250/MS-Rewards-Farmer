import json
import logging
import os
import random
import re
import time
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Literal

import requests
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

from src.browser import Browser
from src.utils import Utils


class Searches:
    def __init__(
        self, browser: Browser, search_source: Literal["trends", "list"] = "list"
    ):
        self.CRYPTO_SEARCH_TERMS = [
            # Major Cryptocurrencies
            "bitcoin",
            "ethereum",
            "solana",
            "link",
            "tao",
            "ondo",
            "optimism",
            "base crypto",
            "ethereum layer 2 networks",
            "arbitrum",
            "polygon",
            "cardano",
            "hbar",
            "ton",
            "inj crypto",
            "kaspa crypto",
            "xrp crypto",
            # DeFi & Infrastructure
            "defi",
            "web3",
            "blockchain",
            "crypto investing",
            "crypto trading",
            "crypto prices news",
            "crypto market",
            "crypto analysis",
            "social media trends in crypto",
            "trending crypto terms on social media",
            # New Tickers from List
            "om crypto",
            "sui crypto",
            "aero crypto",
            "ath crypto",
            "ldo crypto",
            "jto crypto",
            "pol crypto",
            "gno crypto",
            "hype crypto",
            "octa crypto",
            "io crypto",
            "cow crypto",
            "trac crypto",
            "aave crypto",
            "fet crypto",
            "render crypto",
            "orai crypto",
            "prime crypto",
            "virtual crypto",
            "akt crypto",
            "stx crypto",
            "corechain crypto",
            "uni crypto",
            "sei crypto",
            "harry crypto",
            "HarryPotterObamaSonic10Inu crypto",
            "mog crypto",
            "op crypto",
            "mpl crypto",
            "syrup crypto",
            "acx crypto",
            "brett crypto",
            "fartcoin crypto",
            "butthole crypto",
            "retardio crypto",
            "naka crypto",
            "alph crypto",
            "mkr crypto",
            "apu crypto",
            "rio crypto",
            "dione crypto",
            "tia crypto",
            "lockin crypto",
            "imx crypto",
            "popcat crypto",
            "mini crypto",
            "usa crypto",
            "trias crypto",
            "goat crypto",
            "asscoin crypto",
            "hnt crypto",
            "SPX crypto",
            "GIGA crypto",
            "zro crypto",
            "cpool crypto",
            "uni crypto",
            "sei crypto",
            "scf crypto",
        ]
        self.browser = browser
        self.webdriver = browser.webdriver
        self.search_source = search_source
        # Only create results directory and files if using crypto list
        if self.search_source == "list":
            # Create a directory for search results if it doesn't exist
            script_dir = Path(__file__).resolve().parent.parent
            self.results_dir = script_dir / "search_results"
            if not os.path.exists(self.results_dir):
                os.makedirs(self.results_dir)
            # Create a new results file for each day
            self.results_file = (
                self.results_dir
                / f"crypto_search_results_{datetime.now().strftime('%Y%m%d')}.json"
            )
            self.summary_file = (
                self.results_dir
                / f"crypto_search_summary_{datetime.now().strftime('%Y%m%d')}.txt"
            )
            self.search_results = []
        else:
            self.results_dir = None
            self.results_file = None
            self.summary_file = None
            self.search_results = None

    def generateSummary(self):
        """Generate a summary of the search results"""
        try:
            # Group results by search term
            term_results = {}
            for result in self.search_results:
                term = result.get("search_term", "Unknown")
                if term not in term_results:
                    term_results[term] = []
                term_results[term].append(result)

            # Extract price information
            price_pattern = r"\$[\d,]+\.?\d*"
            price_data = {}
            for term, results in term_results.items():
                for result in results:
                    if result.get("price_info"):
                        price_match = re.search(price_pattern, result["price_info"])
                        if price_match:
                            price = float(
                                price_match.group().replace("$", "").replace(",", "")
                            )
                            if term not in price_data:
                                price_data[term] = []
                            price_data[term].append(price)

            # Generate summary
            with open(self.summary_file, "w", encoding="utf-8") as f:
                f.write(
                    f"Crypto Search Summary - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
                )
                f.write("=" * 50 + "\n\n")

                # Price Summary
                f.write("Price Information:\n")
                f.write("-" * 20 + "\n")
                for term, prices in price_data.items():
                    if prices:
                        avg_price = sum(prices) / len(prices)
                        f.write(f"{term}: ${avg_price:,.2f}\n")
                f.write("\n")

                # News and Updates
                f.write("Recent News and Updates:\n")
                f.write("-" * 20 + "\n")
                for term, results in term_results.items():
                    f.write(f"\n{term.upper()}:\n")
                    for result in results:
                        for snippet in result.get("top_results", []):
                            f.write(f"- {snippet['title']}\n")
                            f.write(f"  {snippet['snippet'][:200]}...\n")

                # Error Summary
                errors = [r for r in self.search_results if "error" in r]
                if errors:
                    f.write("\nErrors Encountered:\n")
                    f.write("-" * 20 + "\n")
                    for error in errors:
                        f.write(f"- {error['search_term']}: {error['error']}\n")

            logging.info(f"[SUMMARY] Search summary saved to {self.summary_file}")
        except Exception as e:
            logging.error(f"[SUMMARY] Failed to generate summary: {str(e)}")

    def saveSearchResults(self):
        """Save search results to a JSON file"""
        try:
            with open(self.results_file, "w", encoding="utf-8") as f:
                json.dump(self.search_results, f, indent=2, ensure_ascii=False)
            logging.info(f"[RESULTS] Search results saved to {self.results_file}")
            # Generate summary after saving results
            self.generateSummary()
        except Exception as e:
            logging.error(f"[RESULTS] Failed to save search results: {str(e)}")

    def extractSearchResults(self, search_term: str) -> dict:
        """Extract relevant information from search results"""
        try:
            # Wait for search results to load
            WebDriverWait(self.webdriver, 10).until(
                EC.presence_of_element_located((By.ID, "b_results"))
            )

            # Get the main search results
            results = self.webdriver.find_elements(By.CLASS_NAME, "b_algo")

            # Extract relevant information
            snippets = []
            for result in results[:3]:  # Get top 3 results
                try:
                    title = result.find_element(By.TAG_NAME, "h2").text
                    snippet = result.find_element(By.CLASS_NAME, "b_caption").text
                    snippets.append({"title": title, "snippet": snippet})
                except:
                    continue

            # Look for price information in the knowledge panel
            try:
                price_element = self.webdriver.find_element(By.CLASS_NAME, "b_entityTP")
                price_info = price_element.text
            except:
                price_info = None

            return {
                "search_term": search_term,
                "timestamp": datetime.now().isoformat(),
                "price_info": price_info,
                "top_results": snippets,
            }
        except Exception as e:
            logging.warning(
                f"[RESULTS] Failed to extract results for {search_term}: {str(e)}"
            )
            return {
                "search_term": search_term,
                "timestamp": datetime.now().isoformat(),
                "error": str(e),
            }

    def getGoogleTrends(self, wordsCount: int) -> list:
        # Function to retrieve Google Trends search terms
        searchTerms: list[str] = []
        i = 0
        max_retries = 3

        while len(searchTerms) < wordsCount and i < max_retries:
            i += 1
            try:
                # Fetching daily trends from Google Trends API
                r = requests.get(
                    f"https://trends.google.com/trends/api/dailytrends?hl={self.browser.localeLang}&geo={self.browser.localeGeo}&ns=15"
                )

                # Check if response is valid
                if r.status_code != 200:
                    logging.warning(
                        f"[TRENDS] API returned status code {r.status_code}"
                    )
                    continue

                # Remove the garbage characters that Google prepends
                response_text = r.text
                if response_text.startswith(")]}'"):
                    response_text = response_text[5:]

                # Parse the JSON response
                trends = json.loads(response_text)

                # Extract search terms
                if "default" in trends and "trendingSearchesDays" in trends["default"]:
                    for topic in trends["default"]["trendingSearchesDays"][0][
                        "trendingSearches"
                    ]:
                        searchTerms.append(topic["title"]["query"].lower())
                        searchTerms.extend(
                            relatedTopic["query"].lower()
                            for relatedTopic in topic.get("relatedQueries", [])
                        )
                    searchTerms = list(set(searchTerms))
                else:
                    logging.warning("[TRENDS] Unexpected API response structure")

            except json.JSONDecodeError as e:
                logging.warning(f"[TRENDS] Failed to parse JSON response: {str(e)}")
                continue
            except Exception as e:
                logging.warning(f"[TRENDS] Error fetching trends: {str(e)}")
                continue

        if not searchTerms:
            logging.error("[TRENDS] Failed to get any search terms")
            # Fallback to some basic search terms if API fails
            searchTerms = self.CRYPTO_SEARCH_TERMS[:wordsCount]

        # Ensure we don't return more terms than requested
        return searchTerms[:wordsCount]

    def getRelatedTerms(self, word: str) -> list:
        # Function to retrieve related terms from Bing API
        try:
            r = requests.get(
                f"https://api.bing.com/osjson.aspx?query={word}",
                headers={"User-agent": self.browser.userAgent},
            )
            return r.json()[1]
        except Exception:  # pylint: disable=broad-except
            return []

    def bingSearches(self, numberOfSearches: int, pointsCounter: int = 0):
        # Function to perform Bing searches
        logging.info(
            f"[BING] Starting {self.browser.browserType.capitalize()} Edge Bing searches..."
        )

        try:
            # Get initial points to compare against
            initial_points = self.browser.utils.getBingAccountPoints()
            successful_searches = 0
            points_per_search = (
                5  # Standard points per search, could be different for mobile/desktop
            )

            # Get search terms based on source
            if self.search_source == "trends":
                search_terms = self.getGoogleTrends(numberOfSearches)
                logging.info("[BING] Using Google Trends as search source")
            else:
                search_terms = self.getCryptoList(numberOfSearches)
                logging.info("[BING] Using predefined crypto list as search source")

            if not search_terms:
                logging.error("[BING] Failed to get search terms")
                return pointsCounter

            # Ensure we're on Bing's homepage
            self.webdriver.get("https://bing.com")
            time.sleep(2)  # Wait for page to load

            i = 0
            attempt = 0
            for word in search_terms:
                i += 1
                logging.info(f"[BING] Search {i}/{numberOfSearches}")
                try:
                    current_points = self.bingSearch(word)

                    # Check if points increased from the search
                    if current_points > pointsCounter:
                        successful_searches += 1
                        pointsCounter = current_points
                        attempt = 0  # Reset attempt counter on successful search
                        logging.info(
                            f"[BING] Successful search {successful_searches}/{numberOfSearches}"
                        )
                    else:
                        attempt += 1
                        if attempt >= 2:
                            logging.warning(
                                "[BING] Possible blockage. Refreshing the page."
                            )
                            self.webdriver.refresh()
                            time.sleep(5)  # Wait for refresh
                            attempt = 0
                except Exception as e:
                    logging.warning(f"[BING] Error during search: {str(e)}")
                    attempt += 1
                    if attempt >= 2:
                        logging.warning("[BING] Too many errors. Refreshing the page.")
                        self.webdriver.refresh()
                        time.sleep(5)
                        attempt = 0
                    continue

            # Only save results if using crypto list
            if self.search_source == "list":
                self.saveSearchResults()

            # Log completion status
            points_earned = pointsCounter - initial_points
            logging.info(
                f"[BING] Completed {successful_searches}/{numberOfSearches} searches. "
                f"Points earned: {points_earned}"
            )

            # Return false if we didn't complete all searches
            if successful_searches < numberOfSearches:
                logging.warning(
                    f"[BING] Only completed {successful_searches} out of {numberOfSearches} searches"
                )
                return False

            return True

        except Exception as e:
            logging.error(f"[BING] Critical error during searches: {str(e)}")
            return False

    def bingSearch(self, word: str):
        # Function to perform a single Bing search
        i = 0

        while True:
            try:
                # Ensure we're on Bing's homepage
                if "bing.com" not in self.webdriver.current_url:
                    self.webdriver.get("https://bing.com")
                    time.sleep(2)

                # Wait for search bar and clear it
                self.browser.utils.waitUntilClickable(By.ID, "sb_form_q")
                searchbar = self.webdriver.find_element(By.ID, "sb_form_q")
                searchbar.clear()

                # Add random typing delay to simulate human behavior
                for char in word:
                    searchbar.send_keys(char)
                    time.sleep(
                        random.uniform(0.1, 0.3)
                    )  # Random delay between keystrokes

                # Random delay before submitting
                time.sleep(random.uniform(0.5, 1.5))
                searchbar.submit()

                # Wait for search results to load
                time.sleep(3)

                # Only extract and save search results if using crypto list
                if self.search_source == "list":
                    result_data = self.extractSearchResults(word)
                    self.search_results.append(result_data)

                # Random delay between searches (15-180 seconds)
                time.sleep(Utils.randomSeconds(15, 180))

                # Random number of scrolls (2-4)
                num_scrolls = random.randint(2, 4)
                for _ in range(num_scrolls):
                    # Random scroll amount (50-100% of page height)
                    scroll_amount = random.randint(50, 100)
                    self.webdriver.execute_script(
                        f"window.scrollTo(0, document.body.scrollHeight * {scroll_amount/100});"
                    )
                    # Longer random wait between scrolls (10-15 seconds)
                    time.sleep(Utils.randomSeconds(10, 15))

                return self.browser.utils.getBingAccountPoints()
            except TimeoutException:
                if i == 5:
                    logging.info("[BING] " + "TIMED OUT GETTING NEW PROXY")
                    self.webdriver.proxy = self.browser.giveMeProxy()
                elif i == 10:
                    logging.error(
                        "[BING] "
                        + "Cancelling mobile searches due to too many retries."
                    )
                    return self.browser.utils.getBingAccountPoints()
                self.browser.utils.tryDismissAllMessages()
                logging.error("[BING] " + "Timeout, retrying in 5~ seconds...")
                time.sleep(Utils.randomSeconds(7, 15))
                i += 1
                continue
            except Exception as e:
                logging.error(f"[BING] Error during search: {str(e)}")
                time.sleep(Utils.randomSeconds(5, 10))
                i += 1
                if i >= 10:
                    logging.error("[BING] Too many errors, returning current points")
                    return self.browser.utils.getBingAccountPoints()
                continue

    def getCryptoList(self, wordsCount: int) -> list:
        """Get search terms from the predefined crypto list"""
        # Randomly sample from the list instead of taking sequential items
        return random.sample(
            self.CRYPTO_SEARCH_TERMS, min(wordsCount, len(self.CRYPTO_SEARCH_TERMS))
        )
