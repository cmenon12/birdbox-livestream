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
from datetime import datetime, timedelta
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from enum import Enum, auto
from pathlib import Path

import googleapiclient
from google.auth.transport.requests import Request
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from pytz import timezone

__author__ = "Christopher Menon"
__credits__ = "Christopher Menon"
__license__ = "gpl-3.0"

# The name of the config file
CONFIG_FILENAME = "config.ini"

# File with the OAuth client secret
CLIENT_SECRET_FILE = "client_secret.json"

# API-specific credentials
SCOPES = ["https://www.googleapis.com/auth/youtube"]

# File with the user's access and refresh tokens
TOKEN_PICKLE_FILE = "token.pickle"

# The timezone to use throughout
TIMEZONE = timezone("Europe/London")


class BroadcastTypes(Enum):
    SCHEDULED = auto()
    LIVE = auto()
    FINISHED = auto()
    ALL = auto()


class YouTubeLivestream:

    def __init__(self, config: configparser.SectionProxy):
        self.service = YouTubeLivestream.get_service()

        self.config = config

        self.liveStream = None
        self.scheduled_broadcasts = {}
        self.finished_broadcasts = {}
        self.live_broadcasts = {}

    @staticmethod
    def get_service() -> googleapiclient.discovery.Resource:
        """Authenticates the YouTube API, returning the service.

        :return: the YouTube API service (a Resource)
        :rtype: googleapiclient.discovery.Resource
        """

        LOGGER.info("Authorising service...")

        credentials = None

        # Attempt to access pre-existing credentials
        if os.path.exists(TOKEN_PICKLE_FILE):
            with open(TOKEN_PICKLE_FILE, "rb") as token:
                LOGGER.debug("Loading credentials from %s.", TOKEN_PICKLE_FILE)
                credentials = pickle.load(token)

        # If there are no (valid) credentials available let the user log in
        LOGGER.debug("Credentials are: %s." % str(credentials))
        if not credentials or not credentials.valid:
            if credentials and credentials.expired and credentials.refresh_token:
                LOGGER.debug("Credentials exist but have expired, refreshing...")
                credentials.refresh(Request())
            else:
                LOGGER.debug("Re-authorising credentials.")
                flow = InstalledAppFlow.from_client_secrets_file(
                    CLIENT_SECRET_FILE, SCOPES)
                credentials = flow.run_local_server(port=0)

            # Save the credentials for the next run
            with open(TOKEN_PICKLE_FILE, "wb") as token:
                pickle.dump(credentials, token)

        # Create and return the authenticated service
        service = build("youtube", "v3", credentials=credentials)

        assert os.path.exists(TOKEN_PICKLE_FILE)

        LOGGER.info("Service authorised successfully!\n")
        return service

    def get_stream(self) -> dict:
        """Gets the liveStream, creating it if needed.

        :return: the YouTube liveStream resource
        :rtype: dict
        """

        LOGGER.info("Getting the livestream...")

        # Return the existing stream
        if self.liveStream is not None:
            LOGGER.debug("Returning existing livestream.")
            LOGGER.info("Livestream fetched and returned successfully!\n")
            return self.liveStream

        # Create a new livestream
        LOGGER.debug("Creating a new stream...")
        stream = self.service.liveStreams().insert(
            part="snippet,cdn,contentDetails,id,status",
            body={
                "cdn": {
                    "frameRate": "variable",
                    "ingestionType": "rtmp",
                    "resolution": "variable"
                },
                "contentDetails": {
                    "isReusable": True
                },
                "snippet": {
                    "title": f"Birdbox Livestream at {datetime.now(tz=TIMEZONE).isoformat()}"
                }
            }).execute()
        LOGGER.debug("Stream is: %s.", json.dumps(stream, indent=4))

        # Save and return it
        self.liveStream = stream
        LOGGER.info("Livestream fetched and returned successfully!\n")
        return stream

    def get_stream_url(self) -> str:
        """Gets the liveStream URL, creating it if needed.

        :return: the URL of the liveStream
        :rtype: str
        """

        LOGGER.info("Getting the livestream URL...")

        ingestion_info = self.get_stream()['cdn']['ingestionInfo']
        url = f"{ingestion_info['ingestionAddress']}/{ingestion_info['streamName']}"
        LOGGER.debug("Livestream URL is %s.", url)
        LOGGER.info("Livestream URL fetched and returned successfully!\n")
        return url

    def schedule_broadcast(self, start_time: datetime = datetime.now(tz=TIMEZONE),
                           duration_mins: int = 0):
        """Schedules the live broadcast.

        :param start_time: when the broadcast should start
        :type start_time: datetime.datetime, optional
        :param duration_mins: how long the broadcast will last for in minutes
        :type duration_mins: int, optional
        :return: the YouTube liveBroadcast resource
        :rtype: dict
        """

        LOGGER.info("Scheduling the broadcast...")
        LOGGER.info(locals())

        if duration_mins <= 0:
            duration_mins = self.config["default_duration"]
            LOGGER.debug("Using default duration of %d.", duration_mins)

        # Stop if a broadcast already exists at this time
        if start_time in self.get_broadcasts().keys():
            LOGGER.debug("Returning existing broadcast at %s.", start_time.isoformat())
            LOGGER.info("Broadcast scheduled successfully!\n")
            return self.get_broadcasts()[start_time]

        # Round the end time to the nearest hour
        end_time = start_time + timedelta(minutes=duration_mins)
        LOGGER.debug("End time with no rounding is %s.", end_time.isoformat())
        end_time = end_time.replace(second=0, microsecond=0, minute=0,
                                    hour=end_time.hour) + timedelta(
            hours=end_time.minute // 30)
        LOGGER.debug("End time to the nearest hour is %s.", end_time.isoformat())

        # Schedule a new broadcast
        LOGGER.debug("Scheduling a new broadcast...")
        broadcast = self.service.liveBroadcasts().insert(
            part="id,snippet,contentDetails,status",
            body={
                "contentDetails": {
                    "enableAutoStart": True,
                    "enableAutoStop": False,
                    "enableClosedCaptions": False,
                    "enableDvr": True,
                    "enableEmbed": True,
                    "recordFromStart": True,
                    "startWithSlate": False
                },
                "snippet": {
                    "scheduledStartTime": start_time.isoformat(),
                    "scheduledEndTime": end_time.isoformat(),
                    "title": f"Birdbox on {start_time.strftime('%a %d %b at %H:%M')}"
                },
                "status": {
                    "privacyStatus": self.config["privacy_status"],
                    "selfDeclaredMadeForKids": False
                }
            }).execute()
        LOGGER.debug("Broadcast is: %s.", json.dumps(broadcast, indent=4))

        # Save and return it
        self.scheduled_broadcasts[start_time] = broadcast
        print(f"Scheduled a broadcast at {start_time.isoformat()} till {end_time.isoformat()}")
        LOGGER.info("Broadcast scheduled successfully!\n")
        return broadcast

    def start_broadcast(self, start_time: datetime):
        """Start the broadcast by binding the stream to it.

        :param start_time: when the broadcast should start
        :type start_time: datetime.datetime, optional
        :return: the updated YouTube liveBroadcast resource
        :rtype: dict
        :raises ValueError: if the broadcast at that times doesn't exist
        """

        LOGGER.info("Starting the broadcast...")
        LOGGER.info(locals())

        # Check that this broadcast exists.
        if start_time not in self.scheduled_broadcasts.keys():
            raise ValueError(f"The broadcast at {start_time.isoformat()} is not scheduled!")

        # Bind the broadcast to the stream
        LOGGER.debug("Binding the broadcast to the stream...")
        broadcast = self.service.liveBroadcasts().bind(
            id=self.scheduled_broadcasts[start_time]["id"],
            part="id,snippet,contentDetails,status",
            streamId=self.get_stream()["id"]
        ).execute()
        LOGGER.debug("Broadcast is: %s.", json.dumps(broadcast, indent=4))

        # Save and return it
        self.live_broadcasts[start_time] = broadcast
        self.scheduled_broadcasts.pop(start_time)
        print(f"Started a broadcast at {start_time.isoformat()}")
        LOGGER.info("Broadcast started successfully!\n")
        return broadcast

    def end_broadcast(self, start_time: datetime):
        """End the broadcast by changing it's state to complete.

        :param start_time: when the broadcast should start
        :type start_time: datetime.datetime, optional
        :return: the updated YouTube liveBroadcast resource
        :rtype: dict
        :raises ValueError: if the broadcast at that times doesn't exist
        """

        LOGGER.info("Ending the broadcast...")
        LOGGER.info(locals())

        # Check that this broadcast exists
        if start_time not in self.live_broadcasts.keys():
            raise ValueError(f"The broadcast at {start_time.isoformat()} is not live!")

        # Change its status to complete
        LOGGER.debug("Transitioning the broadcastStatus to complete...")
        broadcast = self.service.liveBroadcasts().transition(
            broadcastStatus="complete",
            id=self.live_broadcasts[start_time]["id"],
            part="id,snippet,contentDetails,status"
        ).execute()
        LOGGER.debug("Broadcast is: %s.", broadcast)

        # Save and return the updated resource
        self.finished_broadcasts[start_time] = broadcast
        self.live_broadcasts.pop(start_time)
        print(f"Ended a broadcast that started at {start_time.isoformat()}")
        LOGGER.info("Broadcast ended successfully!\n")
        return broadcast

    def get_broadcasts(self, category: BroadcastTypes = None) -> dict:
        """Returns a dict with the broadcasts

        :param category: the category of broadcasts if not all
        :type category: BroadcastTypes
        :return: a dict of the broadcasts
        :rtype: dict
        """

        if category == BroadcastTypes.SCHEDULED:
            return self.scheduled_broadcasts
        elif category == BroadcastTypes.LIVE:
            return self.live_broadcasts
        elif category == BroadcastTypes.FINISHED:
            return self.finished_broadcasts
        else:
            return {**self.scheduled_broadcasts, **self.live_broadcasts, **self.finished_broadcasts}


def main():
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
    main_config = parser["main"]
    email_config = parser["email"]

    yt = YouTubeLivestream(yt_config)

    url = yt.get_stream_url()
    print(f"\n{main_config['command']} {url}\n")
    # subprocess.Popen(f"{COMMAND} {url}", shell=True)

    # Schedule the first broadcast
    yt.schedule_broadcast()

    while True:

        scheduled = yt.get_broadcasts(BroadcastTypes.SCHEDULED).copy()
        live = yt.get_broadcasts(BroadcastTypes.LIVE).copy()

        # Schedule broadcasts
        if len(scheduled) < int(main_config["max_scheduled_broadcasts"]):
            last_start_time = max(scheduled.keys())
            last_broadcast = scheduled[last_start_time]
            start_time = datetime.fromisoformat(
                last_broadcast["snippet"]["scheduledEndTime"].replace("Z", "+00:00"))
            yt.schedule_broadcast(start_time)

        # Start broadcasts
        for start_time in scheduled.keys():
            if start_time <= datetime.now(tz=TIMEZONE):
                yt.start_broadcast(start_time)

        # Finish broadcasts
        for start_time in live.keys():
            end_time = datetime.fromisoformat(
                live[start_time]["snippet"]["scheduledEndTime"].replace("Z",
                                                                        "+00:00"))
            if end_time <= datetime.now(tz=TIMEZONE):
                yt.end_broadcast(start_time)


if __name__ == "__main__":

    # Prepare the log
    Path("./logs").mkdir(parents=True, exist_ok=True)
    log_filename = f"./logs/birdbox-livestream-{datetime.now(tz=TIMEZONE).strftime('%Y-%m-%d %H-%M-%S %Z')}.log"
    logging.basicConfig(
        format="%(asctime)s | %(levelname)5s in %(module)s.%(funcName)s() on line %(lineno)-3d | %(message)s",
        level=logging.DEBUG,
        handlers=[
            logging.FileHandler(log_filename, mode="a")
        ])
    LOGGER = logging.getLogger(__name__)

    # Run it
    main()

else:
    LOGGER = logging.getLogger(__name__)
