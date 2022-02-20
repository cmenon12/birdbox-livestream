import configparser
import logging
import time
from datetime import datetime
from pathlib import Path
from typing import Tuple, List

import dvr_scan
import humanize as humanize
import yt_dlp
from dvr_scan.timecode import FrameTimecode
from pytz import timezone

__author__ = "Christopher Menon"
__credits__ = "Christopher Menon"
__license__ = "gpl-3.0"

# The name of the config file
CONFIG_FILENAME = "config.ini"

# How long to wait for authorization (in seconds)
AUTHORIZATION_TIMEOUT = 300

# File with the OAuth client secret
CLIENT_SECRET_FILE = "client_secret.json"

# API-specific credentials
SCOPES = ["https://www.googleapis.com/auth/youtube"]

# File with the user's access and refresh tokens
TOKEN_PICKLE_FILE = "token.pickle"

# The timezone to use throughout
TIMEZONE = timezone("Europe/London")


def download_video(video_id: str):
    ydl_opts = {
        "logger": LOGGER,
        "format": "best[height=144]+[ext=mp4]",
        "verbose": True,
        "final_ext": "mp4"
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        print("here")
        ydl.download(f"https://youtu.be/{video_id}")
        filename = ydl.extract_info(
            f"https://youtu.be/{video_id}")["requested_downloads"][0]["_filename"]

    return filename


def get_motion_timestamps(filename: str):
    """Detect motion and output a list of when it occurs."""

    output = ""
    scan = dvr_scan.scanner.ScanContext([filename])
    scan.set_event_params(
        min_event_len=25 * 5,
        time_pre_event="1s",
        time_post_event="0s")
    result: List[Tuple[FrameTimecode, FrameTimecode,
                       FrameTimecode]] = scan.scan_motion()
    for item in result:
        output += f"{item[0].get_timecode(0)} for {humanize.naturaldelta(item[2].get_seconds())}.\n"
    return output


def main():
    """Runs the motion detection script indefinitely."""

    # Check that the config file exists
    try:
        open(CONFIG_FILENAME)
        LOGGER.info("Loaded config %s.", CONFIG_FILENAME)
    except FileNotFoundError as error:
        print("The config file doesn't exist!")
        LOGGER.info("Could not find config %s, exiting.", CONFIG_FILENAME)
        time.sleep(5)
        raise FileNotFoundError("The config file doesn't exist!") from error

    # Fetch info from the config
    parser = configparser.ConfigParser()
    parser.read(CONFIG_FILENAME)
    yt_config = parser["YouTubeLivestream"]
    main_config = parser["yt_livestream"]
    email_config = parser["email"]

    filename = download_video("eIT3lHx4jq0")
    motion_detected = get_motion_timestamps(filename)
    print(motion_detected)


if __name__ == "__main__":

    # Prepare the log
    Path("./logs").mkdir(parents=True, exist_ok=True)
    log_filename = f"birdbox-livestream-{datetime.now(tz=TIMEZONE).strftime('%Y-%m-%d %H-%M-%S %Z')}.txt"
    log_format = "%(asctime)s | %(levelname)5s in %(module)s.%(funcName)s() on line %(lineno)-3d | %(message)s"
    log_handler = logging.FileHandler(f"./logs/{log_filename}", mode="a")
    log_handler.setFormatter(logging.Formatter(log_format))
    logging.basicConfig(
        format=log_format,
        level=logging.DEBUG,
        handlers=[log_handler])
    LOGGER = logging.getLogger(__name__)

    # Run it
    main()

else:
    LOGGER = logging.getLogger(__name__)
