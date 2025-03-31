import json
import logging
import os
import random
import re
import time
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Literal
import urllib.parse

import requests
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
from bs4 import BeautifulSoup

from src.browser import Browser
from src.utils import Utils


class Searches:
    def __init__(
        self, browser: Browser, search_source: Literal["trends", "crypto"] = "crypto"
    ):
        # Define trusted news sources
        self.NEWS_SOURCES = [
            "CoinDesk",
            "U.Today",
            "Decrypt",
            "Bankless",
            "BeInCrypto",
            "TheBlock",
            "Bitcoin Magazine",
            "Blockworks",
            "Coin Bureau",
            "The Defiant",
            "reddit cryptocurrency",
            "crypto twitter"
        ]
        
        # All tickers from original list, maintaining exact grouping
        self.MAJOR_CRYPTOS = [
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
            "xrp crypto"
        ]
        
        self.OTHER_CRYPTOS = [
            "om mantra crypto",
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
            "sei crypto"
        ]
        
        self.MEME_COINS = [
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
            "scf crypto"
        ]
        
        # Generate comprehensive search terms
        self.CRYPTO_SEARCH_TERMS = []
        
        # Function to add search terms with sources
        def add_with_sources(term_list):
            # Define excluded domains using Bing's -site: operator with wildcards
            excluded_domains = (
                "-site:*coinmarketcap.com -site:*coingecko.com -site:*crypto.com "
                "-site:*etoro.com -site:*tradingview.com -site:*binance.com "
                "-site:*coinbase.com -site:*kraken.com -site:*gemini.com "
                "-site:*bitfinex.com -site:*kucoin.com -site:*huobi.com "
                "-site:*okx.com -site:*bybit.com -site:*gate.io -site:*mexc.com "
                "-site:*aws.amazon.com -site:*cloud.google.com -site:*azure.microsoft.com "
                "-site:*github.com -site:*stackoverflow.com -site:*wikipedia.org "
                "-site:*coincodex.com -site:*livecoinwatch.com -site:*yahoo.com/quote "
            )
            
            # Add language filter, time filter, and exclude non-news content
            search_filters = (
                "language:english freshness:30 "
                "-price -prediction -chart -trade -buy -sell -convert "
                "-tutorial -course -documentation -quote -market -exchange " + excluded_domains
            )
            
            for term in term_list:
                # Add basic term with filters
                self.CRYPTO_SEARCH_TERMS.append(f"{term} news {search_filters}")
                # Add term + source combinations with filters
                for source in self.NEWS_SOURCES:
                    self.CRYPTO_SEARCH_TERMS.append(f"{term} {source} {search_filters}")
        
        # Add all terms with their source combinations
        add_with_sources(self.MAJOR_CRYPTOS)
        add_with_sources(self.OTHER_CRYPTOS)
        add_with_sources(self.MEME_COINS)

        self.browser = browser
        self.webdriver = browser.webdriver
        self.search_source = search_source
        self.test_mode = browser.args.test
        
        # Debug logging
        logging.info(f"[DEBUG] Initializing Searches with search_source: {self.search_source}")
        
        # Only create results directory and files if using crypto
        if self.search_source == "crypto":
            self.results_dir = Path("logs")
            logging.info(f"[DEBUG] Results directory path: {self.results_dir.absolute()}")
            
            # Create a new results file for each day
            self.results_file = (
                self.results_dir
                / f"crypto_search_results_{datetime.now().strftime('%Y%m%d')}.json"
            )
            logging.info(f"[DEBUG] Results file path: {self.results_file.absolute()}")
            
            # Add a file to track remaining search terms
            self.remaining_terms_file = self.results_dir / "remaining_crypto_terms.json"
            
            # Add a file to track seen URLs
            self.seen_urls_file = self.results_dir / "seen_urls.json"
            
            # Initialize empty results list
            self.search_results = []
            
            # Initialize or load remaining terms
            self.remaining_terms = self._load_remaining_terms()
            
            # Initialize or load seen URLs
            self.seen_urls = self._load_seen_urls()
            
            # Try to create an empty file
            try:
                with open(self.results_file, 'a') as f:
                    if self.results_file.stat().st_size == 0:
                        json.dump([], f)
                logging.info(f"[DEBUG] Successfully created/verified results file")
            except Exception as e:
                logging.error(f"[DEBUG] Failed to create results file: {str(e)}")
        else:
            self.results_dir = None
            self.results_file = None
            self.summary_file = None
            self.search_results = None

    def _load_remaining_terms(self) -> list:
        """Load or initialize the list of remaining search terms"""
        try:
            if self.remaining_terms_file.exists():
                with open(self.remaining_terms_file, 'r') as f:
                    terms = json.load(f)
                    if terms:  # If we have remaining terms, use them
                        logging.info(f"[TERMS] Loaded {len(terms)} remaining search terms")
                        return terms
            
            # If file doesn't exist or is empty, start with full list
            logging.info("[TERMS] Starting with fresh search terms list")
            return self.CRYPTO_SEARCH_TERMS.copy()
        except Exception as e:
            logging.error(f"[TERMS] Error loading remaining terms: {str(e)}")
            return self.CRYPTO_SEARCH_TERMS.copy()

    def _save_remaining_terms(self):
        """Save the current list of remaining search terms"""
        try:
            with open(self.remaining_terms_file, 'w') as f:
                json.dump(self.remaining_terms, f, indent=2)
            logging.info(f"[TERMS] Saved {len(self.remaining_terms)} remaining terms")
        except Exception as e:
            logging.error(f"[TERMS] Error saving remaining terms: {str(e)}")

    def _load_seen_urls(self) -> set:
        """Load previously seen URLs from file"""
        try:
            if self.seen_urls_file.exists():
                with open(self.seen_urls_file, 'r') as f:
                    return set(json.load(f))
            return set()
        except Exception as e:
            logging.error(f"[URLS] Error loading seen URLs: {str(e)}")
            return set()

    def _save_seen_urls(self):
        """Save seen URLs to file with size check"""
        try:
            with open(self.seen_urls_file, 'w') as f:
                json.dump(list(self.seen_urls), f)
            
            # Check file size (in GB)
            file_size_gb = self.seen_urls_file.stat().st_size / (1024 * 1024 * 1024)
            if file_size_gb > 250:
                logging.warning(
                    f"[URLS] Warning: seen_urls.json has grown very large ({file_size_gb:.2f} GB). "
                    "Consider archiving or clearing old entries."
                )
        except Exception as e:
            logging.error(f"[URLS] Error saving seen URLs: {str(e)}")

    def extractSearchResults(self, soup) -> dict:
        processed = 0
        try:
            logging.info("[EXTRACT] Starting to extract search results")
            results = []
            main_results = soup.find_all("li", class_="b_algo")
            
            # Add these blocked domains to check against decoded URLs
            blocked_domains = {
                "coinmarketcap.com", "coingecko.com", "crypto.com",
                "etoro.com", "tradingview.com", "binance.com",
                "coinbase.com", "kraken.com", "gemini.com",
                "bitfinex.com", "kucoin.com", "huobi.com",
                "okx.com", "bybit.com", "gate.io", "mexc.com",
                "livecoinwatch.com", "yahoo.com/quote"
            }

            for result in main_results:
                if processed >= 8:
                    break
                    
                try:
                    url_element = result.find("a")
                    if not url_element:
                        continue
                        
                    url = url_element.get("href", "")
                    
                    # Skip if we've seen this URL before
                    if url in self.seen_urls:
                        logging.debug(f"[EXTRACT] Skipping previously seen URL: {url}")
                        continue
                    
                    # Extract actual domain from bing redirect URL
                    if "bing.com/ck/a" in url and "u=a1" in url:
                        try:
                            # Extract and decode the actual URL from Bing's redirect
                            encoded_url = url.split("u=a1")[1].split("&")[0]
                            actual_url = urllib.parse.unquote(encoded_url)
                            domain = urllib.parse.urlparse(actual_url).netloc.lower()
                        except:
                            domain = urllib.parse.urlparse(url).netloc.lower()
                    else:
                        domain = urllib.parse.urlparse(url).netloc.lower()
                    
                    # Skip if domain is in blocked list
                    if any(blocked in domain for blocked in blocked_domains):
                        logging.debug(f"[EXTRACT] Skipping blocked domain: {domain}")
                        continue
                    
                    title = url_element.get_text().strip()
                    main_content = ""
                    
                    snippet_element = result.find("div", class_="b_caption")
                    if snippet_element:
                        p_tags = snippet_element.find_all("p")
                        main_content = " ".join(p.get_text().strip() for p in p_tags if p.get_text())
                    
                    # Format source information
                    source_info = f"Source: {domain}"
                    if any(source.lower() in title.lower() for source in self.NEWS_SOURCES):
                        for source in self.NEWS_SOURCES:
                            if source.lower() in title.lower():
                                title = title.replace(source, "").replace("  ", " ").strip()
                                source_info = f"Source: {source} ({domain})"
                                break
                    
                    result_data = {
                        "title": title,
                        "url": url,
                        "content": main_content,
                        "source": source_info,
                        "timestamp": datetime.now().isoformat()
                    }
                    
                    # Add URL to seen set and append result
                    self.seen_urls.add(url)
                    results.append(result_data)
                    processed += 1
                    
                except Exception as e:
                    logging.debug(f"Error processing individual result: {str(e)}")
                    continue
            
            # Save updated seen URLs after processing
            self._save_seen_urls()
            
            return {
                "results": results,
                "status": "success",
                "timestamp": datetime.now().isoformat(),
                "total_found": len(results)
            }
            
        except Exception as e:
            logging.error(f"Error extracting search results: {str(e)}")
            return {"results": [], "status": "error", "error": str(e)}

    def saveSearchResults(self):
        """Save search results to a JSON file"""
        try:
            if not self.search_results:
                logging.info("[RESULTS] No results to save")
                return
            
            logging.info(f"[RESULTS] Attempting to save {len(self.search_results)} results")
            
            # Load existing results if file exists
            existing_results = []
            if self.results_file.exists():
                try:
                    logging.info(f"[RESULTS] Loading existing results from {self.results_file}")
                    with open(self.results_file, "r", encoding="utf-8") as f:
                        existing_results = json.load(f)
                    logging.info(f"[RESULTS] Loaded {len(existing_results)} existing results")
                except json.JSONDecodeError:
                    logging.warning("[RESULTS] Existing results file was corrupted, starting fresh")

            # Combine existing and new results
            all_results = existing_results + self.search_results
            
            # Write the combined results
            logging.info(f"[RESULTS] Writing {len(all_results)} total results to file")
            with open(self.results_file, "w", encoding="utf-8") as f:
                json.dump(all_results, f, indent=2, ensure_ascii=False)
            
            logging.info(f"[RESULTS] Successfully saved results to {self.results_file}")
            
            # Clear the current results after saving
            self.search_results = []
            
            # Save seen URLs after successful save
            self._save_seen_urls()
            
        except Exception as e:
            logging.error(f"[RESULTS] Failed to save search results: {str(e)}")
            logging.error(f"[RESULTS] Current results count: {len(self.search_results)}")
            logging.error(f"[RESULTS] Results file path: {self.results_file}")

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
        logging.info(
            f"[BING] Starting {self.browser.browserType.capitalize()} Edge Bing searches..."
        )
        if self.test_mode:
            logging.info("[BING] Running in test mode - points checking disabled")

        try:
            # Get initial points to compare against (skip in test mode)
            initial_points = 0 if self.test_mode else self.browser.utils.getBingAccountPoints()

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

                    # Skip points checking in test mode
                    if not self.test_mode:
                        if current_points > pointsCounter:
                            pointsCounter = current_points
                            attempt = 0
                        else:
                            attempt += 1
                            if attempt >= 2:
                                logging.warning("[BING] Possible blockage. Refreshing the page.")
                                self.webdriver.refresh()
                                time.sleep(5)
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

            # Only show points earned if not in test mode
            if not self.test_mode:
                points_earned = pointsCounter - initial_points
                if points_earned > 0:
                    logging.info(f"[BING] Searches completed. Points earned: {points_earned}")
            else:
                logging.info("[BING] Test searches completed")

            return pointsCounter

        except Exception as e:
            logging.error(f"[BING] Critical error during searches: {str(e)}")
            return pointsCounter

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
                if self.search_source == "crypto":
                    try:
                        logging.info(f"[BING] Processing search results for '{word}'")
                        # Create BeautifulSoup object from page source
                        soup = BeautifulSoup(self.webdriver.page_source, 'html.parser')
                        result_data = self.extractSearchResults(soup)
                        
                        if result_data["results"]:
                            logging.info(f"[BING] Found {len(result_data['results'])} results for '{word}'")
                            self.search_results.append({
                                "search_term": word,
                                "timestamp": datetime.now().isoformat(),
                                "results": result_data["results"]
                            })
                            # Save immediately after each successful search
                            logging.info(f"[BING] Saving results for '{word}'")
                            self.saveSearchResults()
                        else:
                            logging.warning(f"[BING] No results found for '{word}'")
                    except Exception as e:
                        logging.error(f"[BING] Error processing search results for '{word}': {str(e)}")
                        logging.exception("Full traceback:")

                # Random delay between searches (15-55 seconds)
                time.sleep(Utils.randomSeconds(3, 33))

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
        """Get search terms from the remaining terms list"""
        if not self.remaining_terms:
            # If we've used all terms, reset the list
            logging.info("[TERMS] Resetting search terms list")
            self.remaining_terms = self.CRYPTO_SEARCH_TERMS.copy()
            self._save_remaining_terms()

        # Take required number of terms
        selected_terms = []
        for _ in range(min(wordsCount, len(self.remaining_terms))):
            # Randomly select and remove a term
            term_index = random.randrange(len(self.remaining_terms))
            selected_terms.append(self.remaining_terms.pop(term_index))
        
        # Save the updated remaining terms
        self._save_remaining_terms()
        
        logging.info(f"[TERMS] Selected {len(selected_terms)} terms, {len(self.remaining_terms)} remaining")
        return selected_terms

    def _cleanup_seen_urls(self, days_to_keep: int = 30):
        """Remove URLs older than specified days from seen set"""
        try:
            # Load all results files from the past N days
            recent_urls = set()
            today = datetime.now()
            for i in range(days_to_keep):
                date = today - timedelta(days=i)
                result_file = self.results_dir / f"crypto_search_results_{date.strftime('%Y%m%d')}.json"
                if result_file.exists():
                    with open(result_file, 'r') as f:
                        data = json.load(f)
                        for search in data:
                            for result in search.get('results', []):
                                recent_urls.add(result['url'])
            
            # Update seen URLs to only include recent ones
            self.seen_urls = recent_urls
            self._save_seen_urls()
            logging.info(f"[URLS] Cleaned up seen URLs, keeping {len(self.seen_urls)} recent URLs")
        except Exception as e:
            logging.error(f"[URLS] Error during URL cleanup: {str(e)}")
