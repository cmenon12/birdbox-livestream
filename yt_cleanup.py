import configparser
import logging
import sys
from datetime import datetime

from pick import pick
from pytz import timezone

__author__ = "Christopher Menon"
__credits__ = "Christopher Menon"
__license__ = "gpl-3.0"

import utilities
from google_services import YouTube

# The name of the config file
CONFIG_FILENAME = "config.ini"

# The timezone to use throughout
TIMEZONE = timezone("Europe/London")

# The filename to use for the log file
LOG_FILENAME = f"birdbox-livestream-yt-livestream-{datetime.now(tz=TIMEZONE).strftime('%Y-%m-%d %H-%M-%S %Z')}.txt"


def main():
    # Get the config
    parser = utilities.load_config(CONFIG_FILENAME)
    yt_config: configparser.SectionProxy = parser["YouTubeLivestream"]

    yt = YouTube(yt_config)

    title = "What do you want to do?"
    options = ["make weekly playlists private", "delete weekly playlists"]
    option, index = pick(options, title)
    LOGGER.info("User chose option %s.", option)

    if option == "make weekly playlists private":
        update_playlists(yt, delete=False, privacy="private")
    elif option == "delete weekly playlists":
        update_playlists(yt, delete=True)


if __name__ == "__main__":

    # Prepare the log
    LOGGER = utilities.prepare_logging(LOG_FILENAME)
    LOGGER.addHandler(logging.StreamHandler(sys.stdout))

    # Run it
    main()

else:
    LOGGER = logging.getLogger(__name__)
