"""Livestream a RTMP stream of a birdbox on YouTube indefinitely.

This script manages the indefinite streaming of a RTMP video stream on
YouTube. It creates one liveStream and multiple consecutive
liveBroadcasts of a pre-defined length, and manages the starting and
stopping of each liveBroadcast. A pre-defined number of liveBroadcasts
are created in advance before being started and stopped on schedule.
"""

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
from typing import Optional, Union

import googleapiclient
from func_timeout import func_set_timeout, FunctionTimedOut
from google.auth.exceptions import RefreshError
from google.auth.transport.requests import Request
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
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


class BroadcastTypes(Enum):
    """The possible types for a broadcast, including an 'all' type."""

    SCHEDULED = auto()
    LIVE = auto()
    FINISHED = auto()
    ALL = auto()


class YouTubeLivestream:
    """Represents a single continuous YouTube livestream.

    :param config: the config to use
    :type config: configparser.SectionProxy
    """

    def __init__(self, config: configparser.SectionProxy):
        self.service = YouTubeLivestream.get_service()

        self.config = config

        self.live_stream = None
        self.week_playlist = None
        self.scheduled_broadcasts = {}
        self.finished_broadcasts = {}
        self.live_broadcasts = {}

    @staticmethod
    def get_service(open_browser: Optional[Union[bool, str]] = False) -> googleapiclient.discovery.Resource:
        """Authenticates the YouTube API, returning the service.

        :return: the YouTube API service (a Resource)
        :rtype: googleapiclient.discovery.Resource
        """

        LOGGER.info("Authorising service...")

        @func_set_timeout(AUTHORIZATION_TIMEOUT)
        def authorize_in_browser():
            """Authorize in the browser, with a timeout."""

            if open_browser is False:
                # Tell the user to go and authorize it themselves
                flow = InstalledAppFlow.from_client_secrets_file(
                    CLIENT_SECRET_FILE, SCOPES,
                    redirect_uri="urn:ietf:wg:oauth:2.0:oob")
                auth_url, _ = flow.authorization_url(prompt="consent")
                print(f"Please visit this URL to authorize this application: {auth_url}")
                print("The URL has been copied to the clipboard.")

                # Get the authorization code
                code = input("Enter the authorization code: ")
                flow.fetch_token(code=code)
                return flow.credentials

            # Else open the browser for the user to authorize it
            flow = InstalledAppFlow.from_client_secrets_file(
                CLIENT_SECRET_FILE, SCOPES)
            print("Your browser should open automatically.")
            return flow.run_local_server(port=0)

        credentials = None

        # Attempt to access pre-existing credentials
        if os.path.exists(TOKEN_PICKLE_FILE):
            with open(TOKEN_PICKLE_FILE, "rb") as token:
                LOGGER.debug("Loading credentials from %s.", TOKEN_PICKLE_FILE)
                credentials = pickle.load(token)

        # If there are no (valid) credentials available let the user log in
        LOGGER.debug("Credentials are: %s.", str(credentials))
        if not credentials or not credentials.valid:
            LOGGER.debug("There are no credentials or they are invalid.")
            if credentials and credentials.refresh_token:
                try:
                    credentials.refresh(Request())
                except RefreshError:
                    os.remove(TOKEN_PICKLE_FILE)

                    try:
                        credentials = authorize_in_browser()
                    except FunctionTimedOut as error:
                        raise FunctionTimedOut(
                            f"Waited {AUTHORIZATION_TIMEOUT} seconds to authorize Google APIs.") from error
            else:
                try:
                    credentials = authorize_in_browser()
                except FunctionTimedOut as error:
                    raise FunctionTimedOut(
                        f"Waited {AUTHORIZATION_TIMEOUT} seconds to authorize Google APIs.") from error

        # If we do have valid credentials then refresh them
        else:
            credentials.refresh(Request())

        # Save the credentials for the next run
        with open(TOKEN_PICKLE_FILE, "wb") as token:
            pickle.dump(credentials, token)
        LOGGER.debug("Credentials saved to %s successfully.",
                     TOKEN_PICKLE_FILE)

        # Create and return the authenticated service
        service = build("youtube", "v3", credentials=credentials)

        assert os.path.exists(TOKEN_PICKLE_FILE)

        LOGGER.info("Service authorised successfully!\n")
        return service

    def get_stream(self) -> dict:
        """Gets the live_stream, creating it if needed.

        :return: the YouTube liveStream resource
        :rtype: dict
        """

        LOGGER.info("Getting the livestream...")

        # Return the existing stream
        if self.live_stream is not None:
            LOGGER.debug("Returning existing livestream.")
            LOGGER.info("Livestream fetched and returned successfully!\n")
            return self.live_stream

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
        LOGGER.debug("Stream is: \n%s.", json.dumps(stream, indent=4))

        # Save and return it
        self.live_stream = stream
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
                           duration_mins: int = 0) -> dict:
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
            duration_mins = int(self.config["default_duration"])
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

        # Create a description
        description = f"A livestream of the birdbox starting on {start_time.strftime('%a %d %b at %H.%M')}" \
                      f" and ending at {end_time.strftime('%H.%M')} ({str(TIMEZONE.zone)} timezone). "

        # Schedule a new broadcast
        LOGGER.debug("Scheduling a new broadcast...")
        broadcast = self.service.liveBroadcasts().insert(
            part="id,snippet,contentDetails,status",
            body={
                "contentDetails": {
                    "enableAutoStart": False,
                    "enableAutoStop": False,
                    "enableClosedCaptions": False,
                    "enableDvr": True,
                    "recordFromStart": True,
                    "startWithSlate": False,
                    "monitorStream": {
                        "enableMonitorStream": False
                    }
                },
                "snippet": {
                    "scheduledStartTime": start_time.isoformat(),
                    "scheduledEndTime": end_time.isoformat(),
                    "title": f"Birdbox on {start_time.strftime('%a %d %b at %H:%M')}",
                    "description": description
                },
                "status": {
                    "privacyStatus": self.config["privacy_status"],
                    "selfDeclaredMadeForKids": False
                }
            }).execute()
        LOGGER.debug("Broadcast is: \n%s.", json.dumps(broadcast, indent=4))

        # Add it to the playlist
        time.sleep(10)
        self.add_to_week_playlist(broadcast["id"], start_time)

        # Save and return it
        self.scheduled_broadcasts[start_time] = broadcast
        print(f"Scheduled a broadcast at {start_time.isoformat()} till {end_time.isoformat()}")
        LOGGER.info("Broadcast scheduled successfully!\n")
        return broadcast

    def start_broadcast(self, start_time: datetime) -> dict:
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
        if start_time not in self.scheduled_broadcasts:
            raise ValueError(f"The broadcast at {start_time.isoformat()} is not scheduled!")

        # Bind the broadcast to the stream
        LOGGER.debug("Binding the broadcast to the stream...")
        broadcast = self.service.liveBroadcasts().bind(
            id=self.scheduled_broadcasts[start_time]["id"],
            part="id,snippet,contentDetails,status",
            streamId=self.get_stream()["id"]
        ).execute()
        LOGGER.debug("Broadcast is: \n%s.", json.dumps(broadcast, indent=4))

        limit = 60
        counter = 0
        LOGGER.debug("Waiting for the stream status to be active...")
        stream_status = self.get_stream_status()
        while stream_status["streamStatus"] != "active" and counter < 5:
            counter += 1
            time.sleep(5)
            stream_status = self.get_stream_status()
        if counter == limit:
            raise TimeoutError(f"Stream status still isn't active after {round(limit * (5 / 60), 2)} minutes!")

        # # Get the broadcast
        # LOGGER.debug("Getting the broadcast...")
        # broadcast_temp = self.service.liveBroadcasts().list(
        #     id=broadcast["id"],
        #     part="id,snippet,contentDetails,status"
        # ).execute()
        # LOGGER.debug("Broadcast is: \n%s.", json.dumps(broadcast_temp, indent=4))

        # Change its status to live
        LOGGER.debug("Transitioning the broadcastStatus to live...")
        try:
            broadcast = self.service.liveBroadcasts().transition(
                broadcastStatus="live",
                id=broadcast["id"],
                part="id,snippet,contentDetails,status"
            ).execute()
            LOGGER.debug("Broadcast is: \n%s.", json.dumps(broadcast, indent=4))
        except googleapiclient.errors.HttpError as error:
            content = ast.literal_eval(error.content.decode("utf-8"))
            if content["error"]["message"] == "Redundant transition":
                LOGGER.debug("Got a redundant transition error, continuing.")
            else:
                raise googleapiclient.errors.HttpError(resp=error.resp, content=error.content) from error
        self.live_broadcasts[start_time] = broadcast
        self.scheduled_broadcasts.pop(start_time)
        print(f"Started a broadcast at {start_time.isoformat()}")

        # Return it
        LOGGER.info("Broadcast started successfully!\n")
        return broadcast

    def end_broadcast(self, start_time: datetime) -> dict:
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
        if start_time not in self.live_broadcasts:
            raise ValueError(f"The broadcast at {start_time.isoformat()} is not live!")

        # Change its status to complete and save it
        LOGGER.debug("Transitioning the broadcastStatus to complete...")
        try:
            broadcast = self.service.liveBroadcasts().transition(
                broadcastStatus="complete",
                id=self.live_broadcasts[start_time]["id"],
                part="id,snippet,contentDetails,status"
            ).execute()
            LOGGER.debug("Broadcast is: \n%s.", json.dumps(broadcast, indent=4))
            self.finished_broadcasts[start_time] = broadcast
        except googleapiclient.errors.HttpError as error:
            content = ast.literal_eval(error.content.decode("utf-8"))
            if content["error"]["message"] == "Redundant transition":
                LOGGER.debug("Got a redundant transition error, continuing.")
                self.finished_broadcasts[start_time] = self.live_broadcasts[start_time]
            else:
                raise googleapiclient.errors.HttpError(resp=error.resp, content=error.content) from error
        self.live_broadcasts.pop(start_time)
        print(f"Ended a broadcast that started at {start_time.isoformat()}")

        # Update the description to point to the next one
        time.sleep(120)
        end_time = datetime.fromisoformat(
            self.finished_broadcasts[start_time]["snippet"]["scheduledEndTime"].replace("Z", "+00:00"))
        broadcasts = self.get_broadcasts(BroadcastTypes.ALL)
        if end_time in broadcasts.keys():
            description = f"{self.finished_broadcasts[start_time]['snippet']['description']} Watch the next part here: https://youtu.be/{broadcasts[end_time]['id']}."
            LOGGER.debug("Updating the description to %s.", description)
            self.update_video_metadata(self.finished_broadcasts[start_time]["id"], description)
        else:
            LOGGER.debug("No next video found (none starting at %s).", str(end_time))
            self.update_video_metadata(self.finished_broadcasts[start_time]["id"])

        # Save and return the updated resource
        LOGGER.info("Broadcast ended successfully!\n")
        return self.finished_broadcasts[start_time]

    def get_broadcasts(self, category: BroadcastTypes = None) -> dict:
        """Returns a dict with the broadcasts

        :param category: the category of broadcasts if not all
        :type category: BroadcastTypes
        :return: a dict of the broadcasts
        :rtype: dict
        """

        if category == BroadcastTypes.SCHEDULED:
            return self.scheduled_broadcasts
        if category == BroadcastTypes.LIVE:
            return self.live_broadcasts
        if category == BroadcastTypes.FINISHED:
            return self.finished_broadcasts
        return {**self.scheduled_broadcasts, **self.live_broadcasts, **self.finished_broadcasts}

    def get_stream_status(self) -> dict:
        """Fetch and return the status of the livestream.

        :return: the status of the livestream.
        :rtype: dict
        """

        stream = self.service.liveStreams().list(
            id=self.get_stream()["id"],
            part="status"
        ).execute()

        LOGGER.debug("Stream status is: %s.", stream["items"][0]["status"])
        return stream["items"][0]["status"]

    def update_video_metadata(self, video_id: str, description: Optional[str] = None) -> None:
        """Update standard video metadata.

        :param video_id: the ID of the video to update
        :type video_id: str
        """

        LOGGER.info("Updating the video metadata...")
        LOGGER.info(locals())

        # Get the existing snippet details
        video = self.service.videos().list(
            id=video_id,
            part="id,snippet"
        ).execute()
        LOGGER.debug("Video is: \n%s.", json.dumps(video, indent=4))

        # Prepare the body
        body = {"snippet": {}}
        body["snippet"]["categoryId"] = self.config["category_id"]
        body["snippet"]["tags"] = ["birdbox", "bird box", "livestream", "live stream", "2022", "bracknell"]
        body["snippet"]["description"] = description if description is not None else video["items"][0]["snippet"][
            "description"]
        body["snippet"]["title"] = video["items"][0]["snippet"]["title"]
        body["snippet"]["defaultLanguage"] = "en-GB"

        LOGGER.debug("Body is: \n%s.", body)

        # Update it
        LOGGER.debug("Updating the video metadata...")
        video = self.service.videos().update(
            part="id,snippet",
            body=body
        ).execute()
        LOGGER.debug("Video is: \n%s.", json.dumps(video, indent=4))

        LOGGER.info("Video metadata updated successfully!")

    def add_to_week_playlist(self, video_id: str, start_time: datetime) -> None:
        """Add the video to the playlist for the week.

        :param video_id: the ID of the video to add
        :type video_id: str
        :param start_time: the start time of the video
        :type start_time: datetime.datetime
        """

        LOGGER.info("Adding the video to the week's playlist...")
        LOGGER.info(locals())

        # Calculate the title
        playlist_title = (start_time - timedelta(days=start_time.weekday())).strftime("W%W: w/c %d %b")

        # Only get the playlist for this week if we don't already have it
        if self.week_playlist is None or self.week_playlist["snippet"]["title"] != playlist_title:

            # Get all the playlists
            # TODO: implement paging
            LOGGER.debug("Fetching all the playlists...")
            all_playlists = []
            response = self.service.playlists().list(
                part="id,snippet",
                mine=True,
                maxResults=50
            ).execute()
            LOGGER.debug("Response is: \n%s.", json.dumps(response, indent=4))
            all_playlists.extend(response["items"])
            LOGGER.debug("Playlists is: \n%s.", json.dumps(all_playlists, indent=4))

            # Try & find this week's playlist
            for item in all_playlists:
                if item["snippet"]["title"] == playlist_title:
                    LOGGER.debug("Using playlist %s.", item)
                    self.week_playlist = item
                    break
            else:
                # Create a new playlist
                LOGGER.debug("Creating a new playlist...")
                description = f"This playlist has videos of the birdbox from {(start_time - timedelta(days=start_time.weekday())).strftime('%a %d %B')} to {(start_time - timedelta(days=start_time.weekday() - 6)).strftime('%a %d %B')}. "
                self.week_playlist = self.service.playlists().insert(
                    part="id,snippet,status",
                    body={
                        "snippet": {
                            "title": playlist_title,
                            "description": description
                        },
                        "status": {
                            "privacyStatus": self.config["privacy_status"]
                        }
                    }
                ).execute()
                LOGGER.debug("Playlist is: \n%s.", json.dumps(self.week_playlist, indent=4))

        # Add the video to the playlist
        playlist_item = self.service.playlistItems().insert(
            part="id,snippet",
            body={
                "snippet": {
                    "playlistId": self.week_playlist["id"],
                    "resourceId": {
                        "videoId": video_id,
                        "kind": "youtube#video"
                    }
                }
            }
        ).execute()
        LOGGER.debug("Playlist Item is: \n%s.", json.dumps(playlist_item, indent=4))

        LOGGER.info("Added the video to the week's playlist successfully!")


def send_error_email(config: configparser.SectionProxy, trace: str,
                     filename: str) -> None:
    """Send an email about the error.

    :param config: the config for the email
    :type config: configparser.SectionProxy
    :param trace: the stack trace of the exception
    :type trace: str
    :param filename: the filename of the log file to attach
    :type filename: str
    :return:
    """

    LOGGER.info("Sending the error email...")

    # Create the message
    message = MIMEMultipart("alternative")
    message["Subject"] = "ERROR with birdbox-livestream!"
    message["To"] = config["to"]
    message["From"] = config["from"]
    message["X-Priority"] = "1"
    message["Date"] = email.utils.formatdate()
    email_id = email.utils.make_msgid(domain=config["smtp_host"])
    message["Message-ID"] = email_id

    # Create and attach the text
    text = f"{trace}\n\n———\nThis email was sent automatically by a computer program (" \
           f"https://github.com/cmenon12/birdbox-livestream). "
    message.attach(MIMEText(text, "plain"))

    LOGGER.debug("Message is: \n%s.", message)

    # Attach the log
    part = MIMEBase("text", "plain")
    part.set_payload(open(f"./logs/{filename}", "r").read())
    encoders.encode_base64(part)
    part.add_header("Content-Disposition",
                    f"attachment; filename=\"{filename}\"")
    part.add_header("Content-Description",
                    f"{filename}")
    message.attach(part)

    # Create the SMTP connection and send the email
    with smtplib.SMTP_SSL(config["smtp_host"],
                          int(config["smtp_port"]),
                          context=ssl.create_default_context()) as server:
        server.login(config["username"], config["password"])
        server.sendmail(re.findall("(?<=<)\\S+(?=>)", config["from"])[0],
                        re.findall("(?<=<)\\S+(?=>)", config["to"]),
                        message.as_string())

    LOGGER.info("Error email sent successfully!\n")


def main():
    """Runs the livestream script indefinitely."""

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

    try:
        yt = YouTubeLivestream(yt_config)

        # Create the stream
        url = yt.get_stream_url()
        print(f"\n{url}\n")
        # print(f"\n{main_config['command']} {url}\n")
        # subprocess.Popen(["./stream.sh", url])

        # Wait for the user to start streaming
        LOGGER.debug("Waiting for the stream status to be active...")
        stream_status = yt.get_stream_status()
        while stream_status["streamStatus"] != "active":
            print(f"Waiting because the stream status is: {stream_status}.")
            time.sleep(5)
            stream_status = yt.get_stream_status()
        print(f"Stream status is: {stream_status}.")

        # Schedule the first broadcast
        yt.schedule_broadcast()

        while True:

            scheduled = yt.get_broadcasts(BroadcastTypes.SCHEDULED).copy()
            live = yt.get_broadcasts(BroadcastTypes.LIVE).copy()

            # Schedule broadcasts
            if len(scheduled) < int(main_config["max_scheduled_broadcasts"]):
                if len(scheduled) != 0:
                    last_start_time = max(scheduled.keys())
                else:
                    last_start_time = max(live.keys())
                last_broadcast = scheduled[last_start_time]
                start_time = datetime.fromisoformat(
                    last_broadcast["snippet"]["scheduledEndTime"].replace("Z", "+00:00"))
                yt.schedule_broadcast(start_time)

            time.sleep(5)

            # Start broadcasts
            for start_time in scheduled.keys():
                if start_time <= datetime.now(tz=TIMEZONE):
                    yt.start_broadcast(start_time)

            time.sleep(5)

            # Finish broadcasts
            for start_time in live.keys():
                end_time = datetime.fromisoformat(
                    live[start_time]["snippet"]["scheduledEndTime"].replace("Z",
                                                                            "+00:00"))
                if end_time <= datetime.now(tz=TIMEZONE):
                    yt.end_broadcast(start_time)

            time.sleep(5)

            # If the time is divisible by 5, log the status
            if datetime.now(tz=TIMEZONE).minute % 5 == 0:
                try:
                    yt.get_stream_status()
                    time.sleep(60)
                except Exception as error:
                    LOGGER.error("\n\n")
                    LOGGER.exception("There was an exception logging the stream status, but we'll carry on anyway.")
                    time.sleep(30)

    except Exception as error:
        LOGGER.error("\n\n")
        LOGGER.exception("There was an exception!!")
        send_error_email(email_config, traceback.format_exc(), log_filename)
        raise Exception from error


if __name__ == "__main__":

    # Prepare the log
    Path("./logs").mkdir(parents=True, exist_ok=True)
    log_filename = f"birdbox-livestream-{datetime.now(tz=TIMEZONE).strftime('%Y-%m-%d %H-%M-%S %Z')}.txt"
    logging.basicConfig(
        format="%(asctime)s | %(levelname)5s in %(module)s.%(funcName)s() on line %(lineno)-3d | %(message)s",
        level=logging.DEBUG,
        handlers=[
            logging.FileHandler(f"./logs/{log_filename}", mode="a")
        ])
    LOGGER = logging.getLogger(__name__)

    # Run it
    main()

else:
    LOGGER = logging.getLogger(__name__)
