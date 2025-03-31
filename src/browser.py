import contextlib
import logging
import os
import random
import socket
import time
from pathlib import Path
from typing import Any

import ipapi
import psutil
import seleniumwire.undetected_chromedriver as webdriver
import undetected_chromedriver as uc
from selenium.webdriver.chrome.webdriver import WebDriver

from src.userAgentGenerator import GenerateUserAgent
from src.utils import Utils


class Browser:
    """WebDriver wrapper class."""

    def __init__(self, mobile: bool, account, args: Any) -> None:
        # Initialize browser instance
        self.mobile = mobile
        self.args = args
        self.browserType = "mobile" if mobile else "desktop"
        
        # Set headless mode: use -v/--visible flag to override account settings
        self.headless = not args.visible if hasattr(args, 'visible') else account.get("headless", False)
        
        self.username = account["username"]
        self.password = account["password"]
        self.localeLang, self.localeGeo = self.getCCodeLang(args.lang, args.geo)
        self.proxy = account.get("proxy", None)
        self.userDataDir = account.get("userDataDir", self.setupProfiles())
        self.browserConfig = account.get("browser", {})
        (
            self.userAgent,
            self.userAgentMetadata,
            newBrowserConfig,
        ) = GenerateUserAgent().userAgent(self.browserConfig, mobile)
        if newBrowserConfig:
            self.browserConfig = newBrowserConfig
            Utils.saveBrowserConfig(self.userDataDir, self.browserConfig)

        # Add retry logic for browser setup
        max_retries = 3
        retry_delay = 5
        for attempt in range(max_retries):
            try:
                # Clean up any existing Chrome processes before starting
                self.cleanupChromeProcesses()
                # Find an available port
                debug_port = self.find_available_port()
                self.webdriver = self.browserSetup(debug_port)
                self.utils = Utils(self.webdriver)
                break
            except Exception as e:
                if attempt == max_retries - 1:
                    logging.error(
                        f"[BROWSER] Failed to initialize browser after {max_retries} attempts: {str(e)}"
                    )
                    raise
                logging.warning(
                    f"[BROWSER] Browser initialization attempt {attempt + 1} failed: {str(e)}"
                )
                time.sleep(retry_delay)
                # Clean up any existing Chrome processes
                self.cleanupChromeProcesses()

    def __enter__(self) -> "Browser":
        return self

    def __exit__(self, *args: Any) -> None:
        # Cleanup actions when exiting the browser context
        self.closeBrowser()

    def closeBrowser(self) -> None:
        """Perform actions to close the browser cleanly."""
        # Close the web browser
        with contextlib.suppress(Exception):
            self.webdriver.quit()

    def find_available_port(self, start_port=9222, max_port=9999):
        """Find an available port for Chrome debugging"""
        for port in range(start_port, max_port + 1):
            try:
                # Try to bind to the port
                with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                    s.bind(("127.0.0.1", port))
                    return port
            except OSError:
                continue
        raise RuntimeError(
            f"Could not find an available port between {start_port} and {max_port}"
        )

    def cleanupChromeProcesses(self):
        """Clean up any existing Chrome processes"""
        try:
            if os.name == 'nt':  # Windows
                os.system('taskkill /F /IM chrome.exe /T 2>nul')
                os.system('taskkill /F /IM chromedriver.exe /T 2>nul')
            else:  # Linux/Mac
                os.system('pkill -f chrome 2>/dev/null')
                os.system('pkill -f chromedriver 2>/dev/null')
            
            # Give processes time to close
            time.sleep(2)
            
            # Try to clean up any lock files in the chrome-temp directory
            chrome_temp = Path("chrome-temp")
            if chrome_temp.exists():
                for file in chrome_temp.glob("*.lock"):
                    try:
                        file.unlink()
                    except Exception as e:
                        logging.debug(f"[BROWSER] Could not remove lock file {file}: {str(e)}")
                    
        except Exception as e:
            logging.warning(f"[BROWSER] Failed to cleanup Chrome processes: {str(e)}")

    def browserSetup(self, debug_port: int) -> WebDriver:
        # Configure and setup the Chrome browser
        options = uc.ChromeOptions()
        options.add_argument("--new-instance")
        
        # Use the existing chrome-temp directory
        chrome_temp_dir = Path("chrome-temp")
        if not chrome_temp_dir.exists():
            chrome_temp_dir.mkdir(parents=True)
        
        options.add_argument(f"--user-data-dir={chrome_temp_dir.absolute()}")

        # Set headless mode
        if self.headless:
            options.add_argument("--headless=new")
            logging.info("[BROWSER] Running in headless mode")
        else:
            logging.info("[BROWSER] Running in visible mode")

        if self.userDataDir:
            options.add_argument(f"--user-data-dir={self.userDataDir}")
        if self.proxy:
            options.add_argument(f"--proxy-server={self.proxy}")

        options.add_argument(f"--lang={self.localeLang}")
        options.add_argument("--log-level=3")
        options.add_argument("--ignore-certificate-errors")
        options.add_argument("--ignore-certificate-errors-spki-list")
        options.add_argument("--ignore-ssl-errors")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-extensions")
        options.add_argument("--dns-prefetch-disable")
        options.add_argument("--disable-gpu")
        options.add_argument("--disable-default-apps")
        options.add_argument("--disable-features=Translate")
        options.add_argument(
            f"--remote-debugging-port={debug_port}"
        )  # Use specific debugging port
        options.add_argument(
            "--disable-dev-shm-usage"
        )  # Overcome limited resource problems
        options.add_argument("--disable-software-rasterizer")
        options.add_argument("--disable-web-security")
        options.add_argument("--disable-site-isolation-trials")

        seleniumwireOptions: dict[str, Any] = {"verify_ssl": False}

        try:
            driver = uc.Chrome(
                options=options,
                seleniumwire_options=seleniumwireOptions,
            )

            seleniumLogger = logging.getLogger("seleniumwire")
            seleniumLogger.setLevel(logging.ERROR)

            if self.browserConfig.get("sizes"):
                deviceHeight = self.browserConfig["sizes"]["height"]
                deviceWidth = self.browserConfig["sizes"]["width"]
            else:
                if self.mobile:
                    deviceHeight = random.randint(568, 1024)
                    deviceWidth = random.randint(320, min(576, int(deviceHeight * 0.7)))
                else:
                    deviceWidth = random.randint(1024, 2560)
                    deviceHeight = random.randint(
                        768, min(1440, int(deviceWidth * 0.8))
                    )
                self.browserConfig["sizes"] = {
                    "height": deviceHeight,
                    "width": deviceWidth,
                }
                Utils.saveBrowserConfig(self.userDataDir, self.browserConfig)

            if self.mobile:
                screenHeight = deviceHeight + 146
                screenWidth = deviceWidth
            else:
                screenWidth = deviceWidth + 55
                screenHeight = deviceHeight + 151

            logging.info(f"Screen size: {screenWidth}x{screenHeight}")
            logging.info(f"Device size: {deviceWidth}x{deviceHeight}")

            if self.mobile:
                driver.execute_cdp_cmd(
                    "Emulation.setTouchEmulationEnabled",
                    {
                        "enabled": True,
                    },
                )

            driver.execute_cdp_cmd(
                "Emulation.setDeviceMetricsOverride",
                {
                    "width": deviceWidth,
                    "height": deviceHeight,
                    "deviceScaleFactor": 0,
                    "mobile": self.mobile,
                    "screenWidth": screenWidth,
                    "screenHeight": screenHeight,
                    "positionX": 0,
                    "positionY": 0,
                    "viewport": {
                        "x": 0,
                        "y": 0,
                        "width": deviceWidth,
                        "height": deviceHeight,
                        "scale": 1,
                    },
                },
            )

            driver.execute_cdp_cmd(
                "Emulation.setUserAgentOverride",
                {
                    "userAgent": self.userAgent,
                    "platform": self.userAgentMetadata["platform"],
                    "userAgentMetadata": self.userAgentMetadata,
                },
            )

            return driver
        except Exception as e:
            logging.error(f"[BROWSER] Failed to setup browser: {str(e)}")
            raise

    def setupProfiles(self) -> Path:
        """
        Sets up the sessions profile for the chrome browser.
        Uses the username to create a unique profile for the session.

        Returns:
            Path
        """
        currentPath = Path(__file__)
        parent = currentPath.parent.parent
        sessionsDir = parent / "sessions"

        # Concatenate username and browser type for a plain text session ID
        sessionid = f"{self.username}"

        sessionsDir = sessionsDir / sessionid
        sessionsDir.mkdir(parents=True, exist_ok=True)
        return sessionsDir

    def getCCodeLang(self, lang: str, geo: str) -> tuple:
        if lang is None or geo is None:
            try:
                nfo = ipapi.location()
                if isinstance(nfo, dict):
                    if lang is None:
                        lang = nfo["languages"].split(",")[0].split("-")[0]
                    if geo is None:
                        geo = nfo["country"]
            except Exception:  # pylint: disable=broad-except
                return ("en", "US")
        return (lang, geo)
