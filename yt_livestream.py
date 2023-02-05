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
from typing import Optional, Dict

import googleapiclient
from pytz import timezone

import google_services
import yt_types

__author__ = "Christopher Menon"
__credits__ = "Christopher Menon"
__license__ = "gpl-3.0"

# The name of the config file
CONFIG_FILENAME = "config.ini"

# The timezone to use throughout
TIMEZONE = timezone("Europe/London")

# The max broadcasts to schedule in advance
MAX_SCHEDULED_BROADCASTS = 2


class BroadcastTypes(Enum):
    """The possible types for a broadcast, including an 'all' type."""

    SCHEDULED = auto()
    LIVE = auto()
    FINISHED = auto()
    ALL = auto()


class YouTubeLivestream(google_services.YouTube):
    """Represents a single continuous YouTube livestream.

    :param config: the config to use
    :type config: configparser.SectionProxy
    """

    def __init__(self, config: configparser.SectionProxy):

        super().__init__(config)

        self.live_stream: Optional[yt_types.YouTubeLiveStream] = None
        self.week_playlist: Optional[yt_types.YouTubePlaylist] = None
        self.scheduled_broadcasts: Dict[datetime,
        yt_types.YouTubeLiveBroadcast] = {}
        self.finished_broadcasts: Dict[datetime,
        yt_types.YouTubeLiveBroadcast] = {}
        self.live_broadcasts: Dict[datetime,
        yt_types.YouTubeLiveBroadcast] = {}

    def get_stream(self) -> yt_types.YouTubeLiveStream:
        """Gets the livestream, creating it if needed.

        :return: the YouTube liveStream resource
        :rtype: yt_types.YouTubeLiveStream
        """

        LOGGER.info("Getting the livestream...")

        # Return the existing stream
        if self.live_stream is not None:
            LOGGER.debug("Returning existing livestream.")
            LOGGER.info("Livestream fetched and returned successfully!\n")
            return self.live_stream

        # Create a new livestream
        LOGGER.debug("Creating a new stream...")
        stream: yt_types.YouTubeLiveStream = self.execute_request(
            self.get_service().liveStreams().insert(
                part="snippet,cdn,contentDetails,id,status",
                body={
                    "cdn": {
                        "frameRate": "variable",
                        "ingestionType": "rtmp",
                        "resolution": "variable"},
                    "contentDetails": {
                        "isReusable": True},
                    "snippet": {
                        "title": f"Birdbox Livestream at {datetime.now(tz=TIMEZONE).isoformat()}"}}))
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

        ingestion_info: yt_types.StreamIngestionInfo = self.get_stream()[
            'cdn']['ingestionInfo']
        url = f"{ingestion_info['ingestionAddress']}/{ingestion_info['streamName']}"
        LOGGER.debug("Livestream URL is %s.", url)
        LOGGER.info("Livestream URL fetched and returned successfully!\n")
        return url

    def schedule_broadcast(
            self,
            start_time: Optional[datetime] = None) -> yt_types.YouTubeLiveBroadcast:
        """Schedules the live broadcast.

        :param start_time: when the broadcast should start
        :type start_time: Optional[datetime]
        :return: the YouTube liveBroadcast resource
        :rtype: yt_types.YouTubeLiveBroadcast
        """

        LOGGER.info("Scheduling the broadcast...")
        LOGGER.info(locals())

        # Use now if not specified
        if not start_time:
            start_time = datetime.now(tz=TIMEZONE)

        # Stop if a broadcast already exists at this time
        if start_time in self.get_broadcasts().keys():
            LOGGER.debug(
                "Returning existing broadcast at %s.",
                start_time.isoformat())
            LOGGER.info("Broadcast scheduled successfully!\n")
            return self.get_broadcasts()[start_time]

        # Round the end time to the nearest 6 hours
        end_time = start_time.astimezone(TIMEZONE) + timedelta(minutes=360)
        LOGGER.debug("End time with no rounding is %s.", end_time.isoformat())

        # If it's going to be tomorrow at midnight
        if round(end_time.hour / 6) * 6 >= 24:
            end_time = end_time.replace(second=0, microsecond=0, minute=0,
                                        hour=0)
            end_time += timedelta(days=1)

        # Otherwise just round
        else:
            end_time = end_time.replace(second=0, microsecond=0, minute=0,
                                        hour=round(end_time.hour / 6) * 6)
        LOGGER.debug(
            "End time to the nearest hour is %s.",
            end_time.isoformat())

        # Create a description
        description = f"A livestream of the birdbox starting on {start_time.strftime('%a %d %b at %H.%M')}" \
                      f" and ending at {end_time.strftime('%H.%M')} ({str(TIMEZONE.zone)} timezone). "

        # Schedule a new broadcast
        LOGGER.debug("Scheduling a new broadcast...")
        broadcast: yt_types.YouTubeLiveBroadcast = self.execute_request(
            self.get_service().liveBroadcasts().insert(
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
                            "enableMonitorStream": False}},
                    "snippet": {
                        "scheduledStartTime": start_time.isoformat(),
                        "scheduledEndTime": end_time.isoformat(),
                        "title": f"Birdbox on {start_time.strftime('%a %d %b at %H:%M')}",
                        "description": description},
                    "status": {
                        "privacyStatus": self.config["privacy_status"],
                        "selfDeclaredMadeForKids": False}}))
        LOGGER.debug("Broadcast is: \n%s.", json.dumps(broadcast, indent=4))

        # Add it to the playlist
        time.sleep(10)
        self.add_to_week_playlist(broadcast["id"], start_time)

        # Save and return it
        self.scheduled_broadcasts[start_time] = broadcast
        print(
            f"Scheduled a broadcast at {start_time.isoformat()} till {end_time.isoformat()}")
        LOGGER.info("Broadcast scheduled successfully!\n")
        return broadcast

    def start_broadcast(
            self,
            start_time: datetime) -> yt_types.YouTubeLiveBroadcast:
        """Start the broadcast by binding the stream to it.

        :param start_time: when the broadcast should start
        :type start_time: datetime
        :return: the updated YouTube liveBroadcast resource
        :rtype: yt_types.YouTubeLiveBroadcast
        :raises ValueError: if the broadcast at that times doesn't exist
        """

        LOGGER.info("Starting the broadcast...")
        LOGGER.info(locals())

        # Check that this broadcast exists.
        if start_time not in self.scheduled_broadcasts:
            raise ValueError(
                f"The broadcast at {start_time.isoformat()} is not scheduled!")

        # Bind the broadcast to the stream
        LOGGER.debug("Binding the broadcast to the stream...")
        broadcast: yt_types.YouTubeLiveBroadcast = self.execute_request(
            self.get_service().liveBroadcasts().bind(
                id=self.scheduled_broadcasts[start_time]["id"],
                part="id,snippet,contentDetails,status",
                streamId=self.get_stream()["id"]))
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
            raise TimeoutError(
                f"Stream status still isn't active after {round(limit * (5 / 60), 2)} minutes!")

        # # Get the broadcast
        # LOGGER.debug("Getting the broadcast...")
        # broadcast_temp: yt_types.YouTubeLiveBroadcastList = self.execute_request(self.get_service().liveBroadcasts().list(
        #     id=broadcast["id"],
        #     part="id,snippet,contentDetails,status"
        # ))
        # LOGGER.debug("Broadcast is: \n%s.", json.dumps(broadcast_temp, indent=4))

        # Change its status to live
        LOGGER.debug("Transitioning the broadcastStatus to live...")
        try:
            broadcast: yt_types.YouTubeLiveBroadcast = self.execute_request(
                self.get_service().liveBroadcasts().transition(
                    broadcastStatus="live",
                    id=broadcast["id"],
                    part="id,snippet,contentDetails,status"))
            LOGGER.debug(
                "Broadcast is: \n%s.",
                json.dumps(
                    broadcast,
                    indent=4))
        except googleapiclient.errors.HttpError as error:
            content = ast.literal_eval(error.content.decode("utf-8"))
            if content["error"]["message"] == "Redundant transition":
                LOGGER.debug("Got a redundant transition error, continuing.")
            else:
                raise googleapiclient.errors.HttpError(
                    resp=error.resp, content=error.content) from error
        self.live_broadcasts[start_time] = broadcast
        self.scheduled_broadcasts.pop(start_time)

        # Update the description to point to the next one
        time.sleep(10)
        end_time = datetime.fromisoformat(
            self.live_broadcasts[start_time]["snippet"]["scheduledEndTime"].replace(
                "Z", "+00:00"))
        broadcasts = self.get_broadcasts(BroadcastTypes.ALL)
        if end_time in broadcasts.keys():
            description = f"{self.live_broadcasts[start_time]['snippet']['description']} Watch the next part here: https://youtu.be/{broadcasts[end_time]['id']}."
            LOGGER.debug("Updating the description to %s.", description)
            self.update_video_metadata(
                self.live_broadcasts[start_time]["id"], description=description)
        else:
            LOGGER.debug(
                "No next video found (none starting at %s).",
                str(end_time))
            self.update_video_metadata(self.live_broadcasts[start_time]["id"])

        # Return it
        print(f"Started a broadcast at {start_time.isoformat()}")
        LOGGER.info("Broadcast started successfully!\n")
        return broadcast

    def end_broadcast(
            self,
            start_time: datetime) -> yt_types.YouTubeLiveBroadcast:
        """End the broadcast by changing it's state to complete.

        :param start_time: when the broadcast should start
        :type start_time: datetime
        :return: the updated YouTube liveBroadcast resource
        :rtype: yt_types.YouTubeLiveBroadcast
        :raises ValueError: if the broadcast at that times doesn't exist
        """

        LOGGER.info("Ending the broadcast...")
        LOGGER.info(locals())

        # Check that this broadcast exists
        if start_time not in self.live_broadcasts:
            raise ValueError(
                f"The broadcast at {start_time.isoformat()} is not live!")

        # Change its status to complete
        LOGGER.debug("Transitioning the broadcastStatus to complete...")
        try:
            broadcast: yt_types.YouTubeLiveBroadcast = self.execute_request(
                self.get_service().liveBroadcasts().transition(
                    broadcastStatus="complete",
                    id=self.live_broadcasts[start_time]["id"],
                    part="id,snippet,contentDetails,status"))
            LOGGER.debug(
                "Broadcast is: \n%s.",
                json.dumps(
                    broadcast,
                    indent=4))
            self.finished_broadcasts[start_time] = broadcast
        except googleapiclient.errors.HttpError as error:
            content = ast.literal_eval(error.content.decode("utf-8"))
            if content["error"]["message"] == "Redundant transition":
                LOGGER.debug("Got a redundant transition error, continuing.")
                self.finished_broadcasts[start_time] = self.live_broadcasts[start_time]
            else:
                raise googleapiclient.errors.HttpError(
                    resp=error.resp, content=error.content) from error

        # Save and return the updated resource
        self.live_broadcasts.pop(start_time)
        print(f"Ended a broadcast that started at {start_time.isoformat()}")
        LOGGER.info("Broadcast ended successfully!\n")
        return self.finished_broadcasts[start_time]

    def get_broadcasts(self,
                       category: BroadcastTypes = None) -> Dict[datetime,
    yt_types.YouTubeLiveBroadcast]:
        """Returns a dict with the broadcasts

        :param category: the category of broadcasts if not all
        :type category: BroadcastTypes
        :return: a dict of the broadcasts
        :rtype: Dict[datetime, yt_types.YouTubeLiveBroadcast]
        """

        if category == BroadcastTypes.SCHEDULED:
            return self.scheduled_broadcasts
        if category == BroadcastTypes.LIVE:
            return self.live_broadcasts
        if category == BroadcastTypes.FINISHED:
            return self.finished_broadcasts
        return {
            **self.scheduled_broadcasts,
            **self.live_broadcasts,
            **self.finished_broadcasts}

    def get_stream_status(self) -> yt_types.StreamStatus:
        """Fetch and return the status of the livestream.

        :return: the status of the livestream
        :rtype: yt_types.StreamStatus
        """

        streams: yt_types.YouTubeLiveStreamList = self.execute_request(
            self.get_service().liveStreams().list(
                id=self.get_stream()["id"], part="status"))

        LOGGER.debug("Stream status is: %s.", streams["items"][0]["status"])
        return streams["items"][0]["status"]

    def update_video_metadata(
            self,
            video_id: str,
            title: Optional[str] = None,
            description: Optional[str] = None) -> None:
        """Update standard video metadata.

        :param video_id: the ID of the video to update
        :type video_id: str
        :param title: the new title
        :type title: Optional[str]
        :param description: the new description
        :type description: Optional[str]
        """

        LOGGER.info("Updating the video metadata...")
        LOGGER.info(locals())

        # Get the existing snippet details
        videos: yt_types.YouTubeVideoList = self.execute_request(
            self.get_service().videos().list(id=video_id, part="id,snippet"))
        LOGGER.debug("Videos is: \n%s.", json.dumps(videos, indent=4))

        # Prepare the body
        body = {"id": video_id, "snippet": {}}
        body["snippet"]["categoryId"] = self.config["category_id"]
        body["snippet"]["tags"] = json.loads(self.config["tags"])
        body["snippet"]["description"] = description if description is not None else videos["items"][0]["snippet"][
            "description"]
        body["snippet"]["title"] = title if title is not None else videos["items"][0]["snippet"]["title"]
        body["snippet"]["defaultLanguage"] = "en-GB"

        LOGGER.debug("Body is: \n%s.", body)

        # Update it
        LOGGER.debug("Updating the video metadata...")
        video: yt_types.YouTubeVideo = self.execute_request(
            self.get_service().videos().update(part="id,snippet", body=body))
        LOGGER.debug("Video is: \n%s.", json.dumps(video, indent=4))

        LOGGER.info("Video metadata updated successfully!")

    def update_video_start_time(self, video_id: str,
                                start_time: Optional[datetime] = None,
                                fail_silently: bool = True) -> None:
        """Update the video start time, leaving everything else in place.

        :param video_id: the ID of the video to update
        :type video_id: str
        :param start_time: the new start time, otherwise now
        :type start_time: Optional[datetime]
        :param fail_silently: whether to skip quietly if it can't be replaced
        :type fail_silently: bool
        """

        LOGGER.info("Updating the video start time...")
        LOGGER.info(locals())

        # Use now if not specified
        if not start_time:
            start_time = datetime.now(tz=TIMEZONE)

        # Get the existing description
        video = self.execute_request(self.get_service().videos().list(
            id=video_id,
            part="id,snippet"
        ))
        LOGGER.debug("Video is: \n%s.", json.dumps(video, indent=4))
        description: str = video["items"][0]["snippet"]["description"]

        # Find and replace it, update it
        if "starting on" in description:
            old_start_time = description[40:59]
            new_description = description.replace(old_start_time, start_time.strftime("%a %d %b at %H.%M"))
            new_title = f"Birdbox on {start_time.strftime('%a %d %b at %H:%M')}"
            self.update_video_metadata(video_id, title=new_title, description=new_description)

        # If asked then raise exception
        elif fail_silently is False:
            raise RuntimeError("Could not update start time!")

        LOGGER.info("Video start time updated successfully!\n")

    def update_video_end_time(self, video_id: str,
                              end_time: Optional[datetime] = None,
                              fail_silently: bool = True) -> None:
        """Set the video end time, leaving everything else in place.

        :param video_id: the ID of the video to update
        :type video_id: str
        :param end_time: the new end time, otherwise now
        :type end_time: Optional[datetime]
        :param fail_silently: whether to skip quietly if it can't be replaced
        :type fail_silently: bool
        """

        LOGGER.info("Updating the video end time...")
        LOGGER.info(locals())

        # Use now if not specified
        if not end_time:
            end_time = datetime.now(tz=TIMEZONE)

        # Get the existing description
        video = self.execute_request(self.get_service().videos().list(
            id=video_id,
            part="id,snippet"
        ))
        LOGGER.debug("Video is: \n%s.", json.dumps(video, indent=4))
        description: str = video["items"][0]["snippet"]["description"]

        # Find and replace it, update it
        if "ending at" in description:
            old_end_time = description[74:79]
            new_description = description.replace(old_end_time,
                                                  end_time.strftime("%H.%M"))
            self.update_video_metadata(video_id, description=new_description)

        # If asked then raise exception
        elif fail_silently is False:
            raise RuntimeError("Could not update end time!")

        LOGGER.info("Video end time updated successfully!\n")

    def add_to_week_playlist(
            self,
            video_id: str,
            start_time: datetime) -> None:
        """Add the video to the playlist for the week.

        :param video_id: the ID of the video to add
        :type video_id: str
        :param start_time: the start time of the video
        :type start_time: datetime.datetime
        """

        LOGGER.info("Adding the video to the week's playlist...")
        LOGGER.info(locals())

        # Calculate the title
        playlist_title = (
                start_time -
                timedelta(
                    days=start_time.weekday())).strftime("W%W: w/c %d %b %Y")

        # Only get the playlist for this week if we don't already have it
        if self.week_playlist is None or self.week_playlist["snippet"]["title"] != playlist_title:

            # Get all the playlists
            all_playlists = self.list_all_playlists()

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
                self.week_playlist: yt_types.YouTubePlaylist = self.execute_request(
                    self.get_service().playlists().insert(
                        part="id,snippet,status", body={
                            "snippet": {
                                "title": playlist_title, "description": description}, "status": {
                                "privacyStatus": self.config["privacy_status"]}}))
                LOGGER.debug(
                    "Playlist is: \n%s.", json.dumps(
                        self.week_playlist, indent=4))

        # Add the video to the playlist
        self.add_to_playlist(video_id, self.week_playlist["id"])

        LOGGER.info("Added the video to the week's playlist successfully!")

    def get_broadcast_status(self, video_id: str) -> yt_types.BroadcastStatus:
        """Fetch and return the status of the broadcast.

        :param video_id: the ID of the video to get
        :type video_id: str
        :return: the status of the broadcast
        :rtype: yt_types.BroadcastStatus
        """

        broadcasts: yt_types.YouTubeLiveBroadcastList = self.execute_request(self.get_service().liveBroadcasts().list(
            id=video_id,
            part="status"
        ))

        LOGGER.debug("Broadcast status of %s is: %s.", video_id, broadcasts["items"][0]["status"])
        return broadcasts["items"][0]["status"]

    def cleanup_unused_broadcasts(self):
        """Cleanup broadcasts that haven't started yet."""

        LOGGER.info("Cleaning up unused broadcasts...")

        # Get all upcoming broadcasts
        LOGGER.debug("Fetching all the upcoming broadcasts...")
        next_page_token = ""
        all_broadcasts = []
        while next_page_token is not None:
            response: yt_types.YouTubeLiveBroadcastList = self.execute_request(
                self.get_service().liveBroadcasts().list(
                    part="id,snippet",
                    broadcastStatus="upcoming",
                    maxResults=50,
                    pageToken=next_page_token))
            LOGGER.debug(
                "Response is: \n%s.", json.dumps(
                    response, indent=4))
            all_broadcasts.extend(response["items"])
            next_page_token = response.get("nextPageToken")
        LOGGER.debug("Broadcasts is: \n%s.",
                     json.dumps(all_broadcasts, indent=4))

        # Stop if there are no upcoming broadcasts
        if len(all_broadcasts) == 0:
            LOGGER.info("No unused broadcasts found!")
            return

        # Get all the playlists
        all_playlists = self.list_all_playlists()

        for broadcast in all_broadcasts:
            if not broadcast["snippet"].get("scheduledStartTime"):
                LOGGER.debug("Broadcast with ID %s has no scheduled start time, skipping.", broadcast["id"])
                continue
            start_time = datetime.strptime(broadcast["snippet"]["scheduledStartTime"], "%Y-%m-%dT%H:%M:%SZ")

            # Calculate the playlist title
            playlist_title = (start_time - timedelta(
                days=start_time.weekday())).strftime("W%W: w/c %d %b %Y")

            # Delete it from the playlist if it exists
            for item in all_playlists:
                if item["snippet"]["title"] == playlist_title:
                    LOGGER.debug("Deleting from playlist %s.", item)
                    self.delete_from_playlist(self, broadcast["id"], item["id"])
                    break

            # Delete the broadcast
            LOGGER.debug("Deleting broadcast %s.", broadcast)
            self.execute_request(self.get_service().liveBroadcasts().delete(id=broadcast["id"]))

        LOGGER.info("Unused broadcasts cleaned up successfully!")


def send_error_email(config: configparser.SectionProxy, trace: str,
                     filename: str) -> None:
    """Send an email about the error.

    :param config: the config for the email
    :type config: configparser.SectionProxy
    :param trace: the stack trace of the exception
    :type trace: str
    :param filename: the filename of the log file to attach
    :type filename: str
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
    email_config = parser["email"]

    try:
        yt = YouTubeLivestream(yt_config)
        yt.cleanup_unused_broadcasts()

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
            now = datetime.now(tz=TIMEZONE)

            # Schedule broadcasts
            if len(scheduled) < int(MAX_SCHEDULED_BROADCASTS):
                if len(scheduled) != 0:
                    last_start_time = max(scheduled.keys())
                else:
                    last_start_time = max(live.keys())
                last_broadcast = scheduled[last_start_time]
                start_time = datetime.fromisoformat(
                    last_broadcast["snippet"]["scheduledEndTime"].replace(
                        "Z", "+00:00")).astimezone(TIMEZONE)
                yt.schedule_broadcast(start_time)

            time.sleep(5)

            # Start broadcasts
            for start_time in scheduled.keys():
                if start_time <= now:
                    yt.start_broadcast(start_time)

                    # Wait until it's actually live (or otherwise done)
                    status = yt.get_broadcast_status(scheduled[start_time]["id"])["lifeCycleStatus"]
                    while status not in ("live", "complete", "revoked"):
                        status = yt.get_broadcast_status(scheduled[start_time]["id"])["lifeCycleStatus"]
                        time.sleep(20)

                    # Update the start time
                    yt.update_video_start_time(scheduled[start_time]["id"])

            time.sleep(5)

            # Finish broadcasts
            for start_time in live.keys():
                end_time = datetime.fromisoformat(
                    live[start_time]["snippet"]["scheduledEndTime"].replace(
                        "Z", "+00:00"))
                if end_time <= now:
                    yt.end_broadcast(start_time)
                    yt.update_video_end_time(live[start_time]["id"])

            time.sleep(5)

            # If the time is divisible by 5, log the stream status
            if now.minute % 5 == 0:
                try:
                    yt.get_stream_status()
                    time.sleep(60)
                except Exception as error:
                    LOGGER.error("\n\n")
                    LOGGER.exception(
                        "There was an exception logging the stream status, but we'll carry on anyway.")
                    time.sleep(30)

    except Exception as error:
        LOGGER.error("\n\n")
        LOGGER.exception("There was an exception!!")
        send_error_email(email_config, traceback.format_exc(), log_filename)
        raise Exception from error


if __name__ == "__main__":

    # Prepare the log
    Path("./logs").mkdir(parents=True, exist_ok=True)
    log_filename = f"birdbox-livestream-yt-livestream-{datetime.now(tz=TIMEZONE).strftime('%Y-%m-%d %H-%M-%S %Z')}.txt"
    logging.basicConfig(
        format="%(asctime)s | %(levelname)5s in %(module)s.%(funcName)s() on line %(lineno)-3d | %(message)s",
        level=logging.DEBUG,
        handlers=[
            logging.FileHandler(
                f"./logs/{log_filename}",
                mode="a",
                encoding="utf-8")])
    LOGGER = logging.getLogger(__name__)

    # Run it
    main()

else:
    LOGGER = logging.getLogger(__name__)
