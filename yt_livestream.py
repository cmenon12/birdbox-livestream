"""Livestream a RTMP stream of a birdbox on YouTube indefinitely.

This script manages the indefinite streaming of a RTMP video stream on
YouTube. It creates one liveStream and multiple consecutive
liveBroadcasts of a pre-defined length, and manages the starting and
stopping of each liveBroadcast. A pre-defined number of liveBroadcasts
are created in advance before being started and stopped on schedule.
"""

import ast
import configparser
import json
import logging
import time
import traceback
from datetime import datetime, timedelta
from enum import Enum, auto
from optparse import OptionParser
from typing import Optional, Dict, List

import googleapiclient
from pytz import timezone

import google_services
import utilities
import yt_types
from utilities import DatetimeFormat as DTFmt

__author__ = "Christopher Menon"
__credits__ = "Christopher Menon"
__license__ = "gpl-3.0"

# The name of the config file
CONFIG_FILENAME = "config.ini"

# The timezone to use throughout
TIMEZONE = timezone("Europe/London")

# The max broadcasts to schedule in advance
MAX_SCHEDULED_BROADCASTS = 2

# The filename to use for the log file
LOG_FILENAME = f"birdbox-livestream-yt-livestream-{datetime.now(tz=TIMEZONE).strftime(DTFmt.datetime_fmt(time_sep='.'))}.txt"


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

        self.livestream_url: Optional[str] = None
        self.livestream_id: Optional[str] = None
        self.week_playlist: Optional[yt_types.YouTubePlaylist] = None
        self.scheduled_broadcasts: Dict[datetime,
        yt_types.YouTubeLiveBroadcast] = {}
        self.finished_broadcasts: Dict[datetime,
        yt_types.YouTubeLiveBroadcast] = {}
        self.live_broadcasts: Dict[datetime,
        yt_types.YouTubeLiveBroadcast] = {}

        if self.validate_livestream_url(str(config["livestream_url"])):
            self.livestream_url = str(config["livestream_url"])
            self.livestream_id = str(config["livestream_id"])

    def create_livestream(self) -> dict[str, str]:
        """Create a new liveStream.

        :return: the YouTube liveStream URL and ID
        :rtype: dict[str, str]
        """

        LOGGER.info("Creating the livestream...")

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
                        "title": f"Birdbox Livestream at {datetime.now(tz=TIMEZONE).strftime(DTFmt.datetime_fmt(tz=True))}"}}))
        LOGGER.debug("Stream is: \n%s.", json.dumps(stream, indent=4))

        # Return it
        ingestion_info: yt_types.StreamIngestionInfo = stream["cdn"]["ingestionInfo"]
        url = f"{ingestion_info['ingestionAddress']}/{ingestion_info['streamName']}"
        LOGGER.info("Livestream URL created and returned successfully!\n")
        return {"url": url, "id": stream["id"]}

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
                start_time.strftime(DTFmt.datetime_fmt(tz=True)))
            LOGGER.info("Broadcast scheduled successfully!\n")
            return self.get_broadcasts()[start_time]

        # Round the end time to the nearest 6 hours
        end_time = start_time.astimezone(TIMEZONE) + timedelta(minutes=360)
        LOGGER.debug("End time with no rounding is %s.",
                     end_time.strftime(DTFmt.datetime_fmt(tz=True)))

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
            end_time.strftime(DTFmt.datetime_fmt(tz=True)))

        # Create a description
        description = f"A livestream of the birdbox starting on {start_time.strftime(DTFmt.pretty_datetime_fmt(time_sep='.', seconds=False))}" \
                      f" and ending at {end_time.strftime(DTFmt.time_fmt(sep='.', seconds=False))} ({str(TIMEZONE.zone)} timezone). "

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
                        "title": f"Birdbox on {start_time.strftime(DTFmt.pretty_datetime_fmt(seconds=False))}",
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
            f"Scheduled a broadcast at {start_time.strftime(DTFmt.datetime_fmt(tz=True))} till {end_time.strftime(DTFmt.datetime_fmt(tz=True))}")
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
                f"The broadcast at {start_time.strftime(DTFmt.datetime_fmt(tz=True))} is not scheduled!")

        # Bind the broadcast to the stream
        LOGGER.debug("Binding the broadcast to the stream...")
        broadcast: yt_types.YouTubeLiveBroadcast = self.execute_request(
            self.get_service().liveBroadcasts().bind(
                id=self.scheduled_broadcasts[start_time]["id"],
                part="id,snippet,contentDetails,status",
                streamId=self.livestream_id))
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
        end_time = self.parse_scheduled_time(
            self.live_broadcasts[start_time]["snippet"]["scheduledEndTime"])
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
        print(
            f"Started a broadcast at {start_time.strftime(DTFmt.datetime_fmt(tz=True))}")
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
                f"The broadcast at {start_time.strftime(DTFmt.datetime_fmt(tz=True))} is not live!")

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
        print(
            f"Ended a broadcast that started at {start_time.strftime(DTFmt.datetime_fmt(tz=True))}")
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

    def list_all_broadcasts(self, part: str, broadcast_status: str = None,
                            broadcast_id: List[str] = None) -> List[yt_types.YouTubeLiveBroadcast]:
        """Fetch and return all the user's broadcasts.

        :param part: the comma-separated properties to fetch
        :type part: str
        :param broadcast_status: the broadcast status of the broadcasts to fetch
        :type broadcast_status: str
        :param broadcast_id: a list of IDs to fetch
        :type broadcast_id: List[str]
        :return: all the broadcasts
        :rtype: List[yt_types.YouTubeLiveBroadcast]
        """

        LOGGER.debug("Fetching all the broadcasts...")
        next_page_token = ""
        all_broadcasts = []
        while next_page_token is not None:
            if broadcast_id:
                response: yt_types.YouTubeLiveBroadcastList = self.execute_request(
                    self.get_service().liveBroadcasts().list(
                        part=part,
                        id=",".join(broadcast_id),
                        maxResults=50,
                        pageToken=next_page_token))
            elif broadcast_status:
                response: yt_types.YouTubeLiveBroadcastList = self.execute_request(
                    self.get_service().liveBroadcasts().list(
                        part=part,
                        broadcastStatus=broadcast_status,
                        maxResults=50,
                        pageToken=next_page_token))
            else:
                response: yt_types.YouTubeLiveBroadcastList = self.execute_request(
                    self.get_service().liveBroadcasts().list(
                        part=part,
                        maxResults=50,
                        pageToken=next_page_token))
            LOGGER.debug("Response is: \n%s.",
                         json.dumps(response, indent=4))
            all_broadcasts.extend(response["items"])
            next_page_token = response.get("nextPageToken")
        LOGGER.debug("Broadcasts is: \n%s.",
                     json.dumps(all_broadcasts, indent=4))

        # Reverse order, so they're oldest first
        all_broadcasts.reverse()

        # Filter by lifecycle status
        valid_broadcasts = []
        status_mappings = {
            "active": ["live", "testing"],
            "all": ["live", "liveStarting", "testStarting", "testing", "complete", "revoked",
                    "created", "ready"],
            "completed": ["complete", "revoked"],
            "upcoming": ["created", "liveStarting", "ready", "testStarting"]
        }
        for broadcast in all_broadcasts:
            if broadcast_status and broadcast["status"]["lifeCycleStatus"] not in status_mappings[
                broadcast_status]:
                continue
            if broadcast_id and broadcast["id"] not in broadcast_id:
                continue
            valid_broadcasts.append(broadcast)

        LOGGER.debug("There are now %s valid broadcasts.", len(valid_broadcasts))
        return valid_broadcasts

    def get_stream_status(self) -> yt_types.StreamStatus:
        """Fetch and return the status of the livestream.

        :return: the status of the livestream
        :rtype: yt_types.StreamStatus
        """

        streams: yt_types.YouTubeLiveStreamList = self.execute_request(
            self.get_service().liveStreams().list(
                id=self.livestream_id, part="status"))

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

    def update_video_times(self, video_id: str,
                           start_time: Optional[datetime] = None,
                           end_time: Optional[datetime] = None,
                           fail_silently: bool = True):
        """Update the video start and/or times, leaving everything else in place.

        :param video_id: the ID of the video to update
        :type video_id: str
        :param start_time: the new start time
        :type start_time: Optional[datetime]
        :param end_time: the new end time
        :type end_time: Optional[datetime]
        :param fail_silently: whether to skip quietly if they can't be replaced
        :type fail_silently: bool
        """

        LOGGER.info("Updating the video times...")
        LOGGER.info(locals())

        # Edge case where both are None
        if start_time is None and end_time is None:
            LOGGER.info("Both start and end time are None, skipping.")
            return

        # Get the existing description
        video = self.execute_request(self.get_service().videos().list(
            id=video_id,
            part="id,snippet"
        ))
        LOGGER.debug("Video is: \n%s.", json.dumps(video, indent=4))
        description: str = video["items"][0]["snippet"]["description"]

        # Find and update the start time
        if start_time is not None:
            if "starting on" in description:
                old_start_time = description[40:64]
                new_description = description.replace(old_start_time, start_time.strftime(
                    DTFmt.pretty_datetime_fmt(time_sep='.', seconds=False)))
                LOGGER.debug("New description is: %s.", new_description)
                new_title = f"Birdbox on {start_time.strftime(DTFmt.pretty_datetime_fmt(seconds=False))}"
                self.update_video_metadata(video_id, title=new_title, description=new_description)

            # If asked then raise exception
            elif fail_silently is False:
                raise RuntimeError("Could not update start time!")

        # Find and update the end time
        if end_time is not None:
            if "ending at" in description:
                old_end_time = description[79:84]
                new_description = description.replace(old_end_time,
                                                      end_time.strftime(
                                                          DTFmt.time_fmt(sep='.',
                                                                         seconds=False)))
                LOGGER.debug("New description is: %s.", new_description)
                self.update_video_metadata(video_id, description=new_description)

            # If asked then raise exception
            elif fail_silently is False:
                raise RuntimeError("Could not update end time!")

        LOGGER.info("Video times updated successfully!\n")

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
                    days=start_time.weekday())).strftime(
            f"W%W: w/c {DTFmt.pretty_date_fmt(day=False)}")

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
                description = f"This playlist has videos of the birdbox from {(start_time - timedelta(days=start_time.weekday())).strftime(DTFmt.pretty_date_fmt(year=False))} to {(start_time - timedelta(days=start_time.weekday() - 6)).strftime(DTFmt.pretty_date_fmt(year=False))}. "
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

        broadcasts = self.list_all_broadcasts(part="status", broadcast_id=[video_id])

        LOGGER.debug("Broadcast status of %s is: %s.", video_id, broadcasts[0]["status"])
        return broadcasts[0]["status"]

    def delete_broadcast(self, video_id: str, start_time: datetime,
                         all_playlists: List[yt_types.YouTubePlaylist] = None):
        """Delete a broadcast and remove it from its playlist."""

        LOGGER.info("Deleting broadcast %s...", video_id)

        # Calculate the playlist title
        playlist_title = (start_time - timedelta(
            days=start_time.weekday())).strftime(
            f"W%W: w/c {DTFmt.pretty_date_fmt(day=False)}")

        if all_playlists is None:
            all_playlists = self.list_all_playlists()

        # Delete it from the playlist if it exists
        for item in all_playlists:
            if item["snippet"]["title"] == playlist_title:
                LOGGER.debug("Deleting from playlist %s.", item)
                self.delete_from_playlist(video_id, item["id"])
                break

        # Delete the broadcast
        LOGGER.debug("Deleting broadcast %s.", video_id)
        self.execute_request(self.get_service().liveBroadcasts().delete(id=video_id))

        LOGGER.info("Broadcast deleted successfully!")

    def cleanup_unused_broadcasts(self):
        """Cleanup broadcasts that haven't started yet."""

        LOGGER.info("Cleaning up unused broadcasts...")

        # Get all upcoming broadcasts
        LOGGER.debug("Fetching all the upcoming broadcasts...")
        all_broadcasts = self.list_all_broadcasts(part="id,snippet,status",
                                                  broadcast_status="upcoming")

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
            start_time = self.parse_scheduled_time(broadcast["snippet"]["scheduledStartTime"])

            self.delete_broadcast(broadcast["id"], start_time, all_playlists)

        LOGGER.info("Unused broadcasts cleaned up successfully!")

    @staticmethod
    def validate_livestream_url(url: str) -> bool:
        """Validate the livestream URL.

        :param url: the URL to validate
        :type url: str
        :return: whether the URL is valid
        :rtype: bool
        """

        return len(url) == 56 and "rtmp.youtube.com" in url and "rtmp://" in url

    @staticmethod
    def parse_scheduled_time(time_str: str) -> datetime:
        """Parse a scheduled time string into a datetime object.

        :param time_str: the time string to parse
        :type time_str: str
        :return: the parsed datetime object
        :rtype: datetime
        """

        return datetime.fromisoformat(time_str.replace("Z", "+00:00")).astimezone(TIMEZONE)


def process_broadcasts(now: datetime, yt: YouTubeLivestream, pause_time: int = 5):
    """Schedule, start, and end the broadcasts."""

    scheduled = yt.get_broadcasts(BroadcastTypes.SCHEDULED).copy()
    live = yt.get_broadcasts(BroadcastTypes.LIVE).copy()

    # Schedule broadcasts
    if len(scheduled) < int(MAX_SCHEDULED_BROADCASTS):
        last_start_time = max(scheduled.keys()) if len(scheduled) != 0 else max(live.keys())
        last_broadcast = scheduled[last_start_time]
        start_time = yt.parse_scheduled_time(last_broadcast["snippet"]["scheduledEndTime"])
        yt.schedule_broadcast(start_time)

    time.sleep(pause_time)

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
            yt.update_video_times(scheduled[start_time]["id"], start_time=datetime.now(tz=TIMEZONE))

    time.sleep(pause_time)

    # Finish broadcasts
    for start_time in live.keys():
        end_time = yt.parse_scheduled_time(live[start_time]["snippet"]["scheduledEndTime"])
        if end_time <= now:
            yt.end_broadcast(start_time)
            yt.update_video_times(live[start_time]["id"], end_time=datetime.now(tz=TIMEZONE))

    time.sleep(pause_time)


def main():
    """Runs the livestream script indefinitely."""

    # Get the config
    parser = utilities.load_config(CONFIG_FILENAME)
    yt_config: configparser.SectionProxy = parser["YouTubeLivestream"]
    email_config: configparser.SectionProxy = parser["email"]

    try:
        yt = YouTubeLivestream(yt_config)

        # Read the options
        opt_parser = OptionParser()
        opt_parser.add_option("--new-stream-url", action="store_true", dest="new_stream_url",
                              default=False)
        options, _ = opt_parser.parse_args()

        # Create a new stream URL and exit if requested
        if options.new_stream_url or not yt.validate_livestream_url(
                str(yt_config["livestream_url"])):
            stream = yt.create_livestream()
            print(f"\nThe new livestream URL is {stream['url']}    \n")
            print(f"\nThe new livestream ID is {stream['id']}    \n")
            print("Save this to the config.ini file and rerun the script.")
            return

        yt.cleanup_unused_broadcasts()

        # Create the stream
        url = str(yt_config["livestream_url"])
        print(f"\n    {url}    \n")

        # Wait for the user to start streaming
        LOGGER.debug("Waiting for the stream status to be active...")
        stream_status = yt.get_stream_status()
        while stream_status["streamStatus"] != "active":
            print(f"Waiting because the stream status is:\n{stream_status}.")
            time.sleep(5)
            stream_status = yt.get_stream_status()
        print(f"Stream status is: {stream_status}.")

        # Schedule the first broadcast
        yt.schedule_broadcast()

        while True:

            now = datetime.now(tz=TIMEZONE)
            process_broadcasts(now, yt)

            # If the time is divisible by 5, log the stream status
            if now.minute % 5 == 0:
                try:
                    yt.get_stream_status()
                    time.sleep(60)
                except Exception:  # pylint: disable=broad-exception-caught
                    LOGGER.error("\n\n")
                    LOGGER.exception(
                        "There was an exception logging the stream status, but we'll carry on anyway.")
                    time.sleep(30)

    except Exception as error:
        LOGGER.exception("\n\nThere was an exception!!")
        utilities.send_error_email(email_config, traceback.format_exc(), LOG_FILENAME)
        raise Exception from error  # pylint: disable=broad-exception-raised


if __name__ == "__main__":

    # Prepare the log
    LOGGER = utilities.prepare_logging(LOG_FILENAME)

    # Run it
    main()

else:
    LOGGER = logging.getLogger(__name__)
