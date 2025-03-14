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
        self.browserType = "mobile" if mobile else "desktop"
        self.headless = not args.visible
        self.username = account["username"]
        self.password = account["password"]
        self.localeLang, self.localeGeo = self.getCCodeLang(args.lang, args.geo)
        self.proxy = None
        if args.proxy:
            self.proxy = args.proxy
        elif account.get("proxy"):
            self.proxy = account["proxy"]
        self.userDataDir = self.setupProfiles()
        self.browserConfig = Utils.getBrowserConfig(self.userDataDir)
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
        """Clean up only Chrome processes created by this script"""
        try:
            # Get the current script's process ID
            current_pid = os.getpid()

            # Get all Chrome processes
            chrome_processes = []
            for proc in psutil.process_iter(["pid", "name", "ppid"]):
                try:
                    # Only target Chrome processes that are children of our script
                    if "chrome" in proc.info["name"].lower() and (
                        proc.info["ppid"] == current_pid
                        or psutil.Process(proc.info["ppid"]).ppid() == current_pid
                    ):
                        chrome_processes.append(proc)
                except (
                    psutil.NoSuchProcess,
                    psutil.AccessDenied,
                    psutil.ZombieProcess,
                ):
                    continue

            # Terminate identified processes
            for proc in chrome_processes:
                try:
                    proc.terminate()
                except (
                    psutil.NoSuchProcess,
                    psutil.AccessDenied,
                    psutil.ZombieProcess,
                ):
                    continue

            time.sleep(1)  # Brief wait to ensure cleanup

        except Exception as e:
            logging.warning(f"[BROWSER] Failed to cleanup Chrome processes: {str(e)}")

    def browserSetup(self, debug_port: int) -> WebDriver:
        # Configure and setup the Chrome browser
        options = uc.ChromeOptions()
        options.add_argument("--new-instance")  # Force new instance
        options.add_argument("--user-data-dir=chrome-temp")  # Use separate user profile

        if self.headless:
            options.add_argument("--headless=new")
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
