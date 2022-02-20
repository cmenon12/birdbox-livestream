import ast
import configparser
import email.utils
import json
import logging
import os
import pickle
import re
import smtplib
import ssl
import time
import traceback
from datetime import datetime, timedelta
from email import encoders
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from enum import Enum, auto
from pathlib import Path
from typing import Optional, Union, Any

import googleapiclient
import yt_dlp
from func_timeout import func_set_timeout, FunctionTimedOut
from google.auth.exceptions import RefreshError
from google.auth.transport.requests import Request
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from pytz import timezone

import yt_livestream

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


def run_motion_detection(service: googleapiclient.discovery.Resource, video_id: str):
    # Download the video
    ydl_opts = {
        "logger": LOGGER,
        "format": "best[height=144]+[ext=mp4]",
        "verbose": True,
        "final_ext": "mp4"
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        print("here")
        ydl.download(f"https://youtu.be/{video_id}")
        filename = ydl.extract_info(f"https://youtu.be/{video_id}")["requested_downloads"][0]["_filename"]


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

    service = yt_livestream.YouTubeLivestream.get_service()
    run_motion_detection(None, "CRtFmfYqipE")


if __name__ == "__main__":

    # Prepare the log
    Path("./logs").mkdir(parents=True, exist_ok=True)
    log_filename = f"birdbox-livestream-{datetime.now(tz=TIMEZONE).strftime('%Y-%m-%d %H-%M-%S %Z')}.txt"
    logging.basicConfig(
        format="%(asctime)s | %(levelname)5s in %(module)s.%(funcName)s() on line %(lineno)-3d | %(message)s",
        level=logging.DEBUG,
        handlers=[
            logging.FileHandler(
                f"./logs/{log_filename}",
                mode="a")])
    LOGGER = logging.getLogger(__name__)

    # Run it
    main()

else:
    LOGGER = logging.getLogger(__name__)
