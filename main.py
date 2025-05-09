# searches the crypto list by default

# Use a flag for Google Trends for search terms instead
# python main.py -s trends

# Or with the long form
# python main.py --search-source trends

import argparse
import atexit
import csv
import json
import logging
import logging.handlers as handlers
import os
import random
import re
import sys
import time
from datetime import datetime
from pathlib import Path

import pandas as pd
import psutil

from src import (
    Browser,
    DailySet,
    Login,
    MorePromotions,
    PunchCards,
    Searches,
    VersusGame,
)
from src.completion_status import CompletionStatus
from src.loggingColoredFormatter import ColoredFormatter
from src.notifier import Notifier
from src.utils import Utils

POINTS_COUNTER = 0


def main():
    print("test", Utils.randomSeconds(5, 10))
    args = argumentParser()
    notifier = Notifier(args)
    setupLogging(args.verbosenotifs, notifier)
    loadedAccounts = setupAccounts()
    # Register the cleanup function to be called on script exit
    atexit.register(cleanupChromeProcesses)
    # Load previous day's points data
    previous_points_data = load_previous_points_data()
    # Initialize completion status tracker
    completion_status = CompletionStatus()
    completion_status.clear_old_status()  # Clean up old status entries

    # Process accounts
    for currentAccount in loadedAccounts:
        process_account_with_retry(
            currentAccount, notifier, args, previous_points_data, completion_status
        )

    # Save the current day's points data for the next day in the "logs" folder
    save_previous_points_data(previous_points_data)
    logging.info("[POINTS] Data saved for the next day.")


def log_daily_points_to_csv(date, earned_points, points_difference):
    logs_directory = Path(__file__).resolve().parent / "logs"
    csv_filename = logs_directory / "points_data.csv"

    # Create a new row with the date, daily points, and points difference
    date = datetime.now().strftime("%Y-%m-%d")
    new_row = {
        "Date": date,
        "Earned Points": earned_points,
        "Points Difference": points_difference,
    }

    fieldnames = ["Date", "Earned Points", "Points Difference"]
    is_new_file = not csv_filename.exists()

    with open(csv_filename, mode="a", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames)

        if is_new_file:
            writer.writeheader()

        writer.writerow(new_row)


def setupLogging(verbose_notifs, notifier):
    ColoredFormatter.verbose_notifs = verbose_notifs
    ColoredFormatter.notifier = notifier

    format = "%(asctime)s [%(levelname)s] %(message)s"
    terminalHandler = logging.StreamHandler(sys.stdout)
    terminalHandler.setFormatter(ColoredFormatter(format))

    logs_directory = Path(__file__).resolve().parent / "logs"
    logs_directory.mkdir(parents=True, exist_ok=True)

    logging.basicConfig(
        level=logging.INFO,
        format=format,
        handlers=[
            handlers.TimedRotatingFileHandler(
                logs_directory / "activity.log",
                when="midnight",
                interval=1,
                backupCount=2,
                encoding="utf-8",
            ),
            terminalHandler,
        ],
    )


def cleanupChromeProcesses():
    # Get the current user's PID
    current_pid = os.getpid()

    try:
        # Get all chrome processes
        for proc in psutil.process_iter(["pid", "name", "ppid"]):
            try:
                # Only terminate Chrome processes that are children of our script
                if (
                    proc.info["name"].lower().startswith(("chrome", "chromedriver"))
                    and proc.info["ppid"] == current_pid
                ):
                    proc.terminate()
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                pass
    except Exception as e:
        logging.warning(f"Error while cleaning up Chrome processes: {e}")


def argumentParser() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="MS Rewards Farmer")
    parser.add_argument(
        "-v", "--visible",
        action="store_true",
        help="Optional: Show the browser window (disable headless mode)",
    )
    parser.add_argument(
        "-l", "--lang", type=str, default=None, help="Optional: Language (ex: en)"
    )
    parser.add_argument(
        "-g", "--geo", type=str, default=None, help="Optional: Geolocation (ex: US)"
    )
    parser.add_argument(
        "-p",
        "--proxy",
        type=str,
        default=None,
        help="Optional: Global Proxy (ex: http://user:pass@host:port)",
    )
    parser.add_argument(
        "-t",
        "--telegram",
        metavar=("TOKEN", "CHAT_ID"),
        nargs=2,
        type=str,
        default=None,
        help="Optional: Telegram Bot Token and Chat ID (ex: 123456789:ABCdefGhIjKlmNoPQRsTUVwxyZ 123456789)",
    )
    parser.add_argument(
        "-d",
        "--discord",
        type=str,
        default=None,
        help="Optional: Discord Webhook URL (ex: https://discord.com/api/webhooks/123456789/ABCdefGhIjKlmNoPQRsTUVwxyZ)",
    )
    parser.add_argument(
        "-vn",
        "--verbosenotifs",
        action="store_true",
        help="Optional: Send all the logs to discord/telegram",
    )
    parser.add_argument(
        "-cv",
        "--chromeversion",
        type=int,
        default=None,
        help="Optional: Set fixed Chrome version (ex. 118)",
    )
    parser.add_argument(
        "-s",
        "--search-source",
        type=str,
        choices=["trends", "crypto"],
        default="crypto",
        help="Optional: Source for search terms (trends: Google Trends, crypto: predefined crypto list)",
    )
    parser.add_argument(
        "--test",
        action="store_true",
        help="Optional: Run in test mode (bypasses points checking and completion status)",
    )
    return parser.parse_args()


def setupAccounts() -> list:
    """Sets up and validates a list of accounts loaded from 'accounts.json'."""

    def validEmail(email: str) -> bool:
        """Validate Email."""
        pattern = r"^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$"
        return bool(re.match(pattern, email))

    accountPath = Path(__file__).resolve().parent / "accounts.json"
    if not accountPath.exists():
        accountPath.write_text(
            json.dumps(
                [{"username": "Your Email", "password": "Your Password"}], indent=4
            ),
            encoding="utf-8",
        )
        noAccountsNotice = """
    [ACCOUNT] Accounts credential file "accounts.json" not found.
    [ACCOUNT] A new file has been created, please edit with your credentials and save.
    """
        logging.warning(noAccountsNotice)
        exit()
    loadedAccounts = json.loads(accountPath.read_text(encoding="utf-8"))
    for account in loadedAccounts:
        if not validEmail(account["username"]):
            logging.error(f"[CREDENTIALS] Wrong Email Address: '{account['username']}'")
            exit()
    random.shuffle(loadedAccounts)
    return loadedAccounts


def executeBot(
    currentAccount,
    notifier: Notifier,
    args: argparse.Namespace,
    completion_status: CompletionStatus,
):
    logging.info(
        f'********************{currentAccount.get("username", "")}********************'
    )
    accountPointsCounter = 0
    remainingSearches = 0
    remainingSearchesM = 0
    startingPoints = 0
    account_email = currentAccount.get("username", "")

    with Browser(mobile=False, account=currentAccount, args=args) as desktopBrowser:
        accountPointsCounter = Login(desktopBrowser).login()
        startingPoints = accountPointsCounter
        if startingPoints == "Locked":
            notifier.send("🚫 Account is Locked", currentAccount)
            return 0
        if startingPoints == "Verify":
            notifier.send("❗ Account needs to be verified", currentAccount)
            return 0

        logging.info(
            f"[POINTS] You have {desktopBrowser.utils.formatNumber(accountPointsCounter)} points on your account"
        )

        # Only complete daily set if not already done
        if not completion_status.is_completed(account_email, "daily_set"):
            DailySet(desktopBrowser).completeDailySet()
            completion_status.mark_completed(account_email, "daily_set")
        else:
            logging.info("[DAILY SET] Skipping as it was already completed")

        # Only complete punch cards if not already done
        if not completion_status.is_completed(account_email, "punch_cards"):
            PunchCards(desktopBrowser).completePunchCards()
            completion_status.mark_completed(account_email, "punch_cards")
        else:
            logging.info("[PUNCH CARDS] Skipping as it was already completed")

        # Only complete more promotions if not already done
        if not completion_status.is_completed(account_email, "more_promotions"):
            MorePromotions(desktopBrowser).completeMorePromotions()
            completion_status.mark_completed(account_email, "more_promotions")
        else:
            logging.info("[MORE PROMOS] Skipping as it was already completed")

        # VersusGame(desktopBrowser).completeVersusGame()
        (
            remainingSearches,
            remainingSearchesM,
        ) = desktopBrowser.utils.getRemainingSearches()

        # Introduce random pauses before and after searches
        pause_before_search = random.uniform(
            11.0, 15.0
        )  # Random pause between 11 to 15 seconds
        time.sleep(pause_before_search)

        # Only do desktop searches if not already completed
        if args.test:
            # In test mode, always do searches regardless of completion status
            accountPointsCounter = Searches(
                desktopBrowser, search_source=args.search_source
            ).bingSearches(remainingSearches)
        elif remainingSearches != 0 and not completion_status.is_completed(
            account_email, "desktop_searches"
        ):
            accountPointsCounter = Searches(
                desktopBrowser, search_source=args.search_source
            ).bingSearches(remainingSearches)
            completion_status.mark_completed(account_email, "desktop_searches")
        elif completion_status.is_completed(account_email, "desktop_searches"):
            logging.info(
                "[BING] Skipping desktop searches as they were already completed"
            )

        pause_after_search = random.uniform(
            11.0, 15.0
        )  # Random pause between 11 to 15 seconds
        time.sleep(pause_after_search)

        desktopBrowser.utils.goHome()
        goalPoints = desktopBrowser.utils.getGoalPoints()
        goalTitle = desktopBrowser.utils.getGoalTitle()
        desktopBrowser.closeBrowser()

    # Only do mobile searches if not already completed
    if args.test:
        # In test mode, always do mobile searches
        desktopBrowser.closeBrowser()
        with Browser(mobile=True, account=currentAccount, args=args) as mobileBrowser:
            accountPointsCounter = Login(mobileBrowser).login()
            accountPointsCounter = Searches(
                mobileBrowser, search_source=args.search_source
            ).bingSearches(remainingSearchesM)
    elif remainingSearchesM != 0 and not completion_status.is_completed(
        account_email, "mobile_searches"
    ):
        desktopBrowser.closeBrowser()
        with Browser(mobile=True, account=currentAccount, args=args) as mobileBrowser:
            accountPointsCounter = Login(mobileBrowser).login()
            accountPointsCounter = Searches(
                mobileBrowser, search_source=args.search_source
            ).bingSearches(remainingSearchesM)
            completion_status.mark_completed(account_email, "mobile_searches")

            mobileBrowser.utils.goHome()
            goalPoints = mobileBrowser.utils.getGoalPoints()
            goalTitle = mobileBrowser.utils.getGoalTitle()
            mobileBrowser.closeBrowser()
    elif completion_status.is_completed(account_email, "mobile_searches"):
        logging.info("[BING] Skipping mobile searches as they were already completed")

    logging.info(
        f"[POINTS] You have earned {desktopBrowser.utils.formatNumber(accountPointsCounter - startingPoints)} points today !"
    )
    logging.info(
        f"[POINTS] You are now at {desktopBrowser.utils.formatNumber(accountPointsCounter)} points !"
    )
    goalNotifier = ""
    if goalPoints > 0:
        logging.info(
            f"[POINTS] You are now at {(desktopBrowser.utils.formatNumber((accountPointsCounter / goalPoints) * 100))}% of your goal ({goalTitle}) !\n"
        )
        goalNotifier = f"🎯 Goal reached: {(desktopBrowser.utils.formatNumber((accountPointsCounter / goalPoints) * 100))}% ({goalTitle})"

    notifier.send(
        "\n".join(
            [
                f"⭐️ Points earned today: {desktopBrowser.utils.formatNumber(accountPointsCounter - startingPoints)}",
                f"💰 Total points: {desktopBrowser.utils.formatNumber(accountPointsCounter)}",
                goalNotifier,
            ]
        ),
        currentAccount,
    )

    return accountPointsCounter


def export_points_to_csv(points_data):
    logs_directory = Path(__file__).resolve().parent / "logs"
    csv_filename = logs_directory / "points_data.csv"
    with open(csv_filename, mode="a", newline="") as file:  # Use "a" mode for append
        fieldnames = ["Account", "Earned Points", "Points Difference"]
        writer = csv.DictWriter(file, fieldnames=fieldnames)

        # Check if the file is empty, and if so, write the header row
        if file.tell() == 0:
            writer.writeheader()

        for data in points_data:
            writer.writerow(data)


# Define a function to load the previous day's points data from a file in the "logs" folder
def load_previous_points_data():
    logs_directory = Path(__file__).resolve().parent / "logs"
    try:
        with open(logs_directory / "previous_points_data.json", "r") as file:
            return json.load(file)
    except FileNotFoundError:
        return {}


# Define a function to save the current day's points data for the next day in the "logs" folder
def save_previous_points_data(data):
    logs_directory = Path(__file__).resolve().parent / "logs"
    with open(logs_directory / "previous_points_data.json", "w") as file:
        json.dump(data, file, indent=4)


def process_account_with_retry(
    currentAccount, notifier, args, previous_points_data, completion_status
):
    retries = 3
    while retries > 0:
        try:
            earned_points = executeBot(
                currentAccount, notifier, args, completion_status
            )
            account_name = currentAccount.get("username", "")
            previous_points = previous_points_data.get(account_name, 0)

            # Calculate the difference in points from the prior day
            points_difference = earned_points - previous_points

            # Append the daily points and points difference to CSV and Excel
            log_daily_points_to_csv(account_name, earned_points, points_difference)

            # Update the previous day's points data
            previous_points_data[account_name] = earned_points

            logging.info(f"[POINTS] Data for '{account_name}' appended to the file.")
            break  # Exit the loop if execution is successful
        except Exception as e:
            retries -= 1
            if retries == 0:
                notifier.send(
                    "⚠️ Error occurred after 3 attempts, please check the log",
                    currentAccount,
                )
                logging.error(
                    f"[CRITICAL] ⚠️ Error occurred after 3 attempts. Closing script!⚠️ | {currentAccount.get('username', '')}"
                )
            else:
                account_name2 = currentAccount.get("username", "")
                logging.warning(f"Error occurred: {e}. Retrying... | {account_name2}")
                time.sleep(10)  # Wait a bit before retrying


if __name__ == "__main__":
    main()
