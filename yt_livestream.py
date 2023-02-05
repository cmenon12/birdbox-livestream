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
from typing import Optional, Any, Dict, List

import googleapiclient
from func_timeout import func_set_timeout, FunctionTimedOut
from google.auth.exceptions import RefreshError
from google.auth.transport.requests import Request
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from pushbullet import InvalidKeyError, PushError, Pushbullet
from pytz import timezone

import yt_types

__author__ = "Christopher Menon"
__credits__ = "Christopher Menon"
__license__ = "gpl-3.0"

# The name of the config file
CONFIG_FILENAME = "config.ini"

# How long to wait for authorisation (in seconds)
AUTHORISATION_TIMEOUT = 600

# File with the OAuth client secret
CLIENT_SECRET_FILE = "client_secret.json"

# API-specific credentials
SCOPES = ["https://www.googleapis.com/auth/youtube"]

# File with the user's access and refresh tokens
TOKEN_PICKLE_FILE = "token.pickle"

# The timezone to use throughout
TIMEZONE = timezone("Europe/London")

# The max broadcasts to schedule in advance
MAX_SCHEDULED_BROADCASTS = 2


class AuthorisationTypes(Enum):
    """The possible types for API authorisation"""

    SSH = auto()
    PUSHBULLET = auto()
    BROWSER = auto()


class YouTube:
    """Represents the YouTube API.

    :param config: the config to use
    :type config: configparser.SectionProxy
    """

    def __init__(self, config: configparser.SectionProxy):

        self.config = config

    def get_service(
            self,
            auth_type: AuthorisationTypes = AuthorisationTypes.PUSHBULLET,
            token_file=TOKEN_PICKLE_FILE) -> googleapiclient.discovery.Resource:
        """Authenticates the YouTube API, returning the service.

        :return: the YouTube API service (a Resource)
        :rtype: googleapiclient.discovery.Resource
        """

        LOGGER.info("Authorising service...")

        @func_set_timeout(AUTHORISATION_TIMEOUT)
        def authorise():
            """Authorise the request."""

            # Open the browser for the user to authorise it
            if auth_type is AuthorisationTypes.BROWSER:
                flow = InstalledAppFlow.from_client_secrets_file(
                    CLIENT_SECRET_FILE, SCOPES)
                print("Your browser should open automatically.")
                return flow.run_local_server(port=0)

            # Tell the user to authorise it themselves
            else:
                flow = InstalledAppFlow.from_client_secrets_file(
                    CLIENT_SECRET_FILE, SCOPES,
                    redirect_uri="urn:ietf:wg:oauth:2.0:oob")
                auth_url, _ = flow.authorization_url(prompt="consent")
                print(
                    f"Please visit this URL to authorise this application: {auth_url}")
                if auth_type is AuthorisationTypes.PUSHBULLET and str(
                        self.config["pushbullet_access_token"]).lower() != "false":
                    print("Requesting via Pushbullet...")
                    code = self.pushbullet_request_response(
                        "YT API Authorisation", auth_url)
                else:
                    code = input("Enter the authorisation code: ")
                flow.fetch_token(code=code)
                return flow.credentials

        # Attempt to access pre-existing credentials
        if os.path.exists(token_file):
            with open(token_file, "rb") as token:
                LOGGER.debug("Loading credentials from %s.", token_file)
                credentials = pickle.load(token)

            # Try to refresh the credentials
            LOGGER.debug("Credentials are: %s.", str(credentials))
            try:
                credentials.refresh(Request())
            except RefreshError:
                os.remove(token_file)
                try:
                    credentials = authorise()
                except FunctionTimedOut as error:
                    raise FunctionTimedOut(
                        f"Waited {AUTHORISATION_TIMEOUT} seconds to authorise Google APIs.") from error

        # If they don't exist then get some new ones
        else:
            try:
                credentials = authorise()
            except FunctionTimedOut as error:
                raise FunctionTimedOut(
                    f"Waited {AUTHORISATION_TIMEOUT} seconds to authorise Google APIs.") from error

        # Save the credentials for the next run
        with open(token_file, "wb") as token:
            pickle.dump(credentials, token)
        LOGGER.debug("Credentials saved to %s successfully.",
                     token_file)

        # Create and return the authenticated service
        service = build("youtube", "v3", credentials=credentials)

        assert os.path.exists(token_file)

        LOGGER.info("Service authorised successfully!\n")
        return service

    @staticmethod
    def execute_request(request: googleapiclient.http.HttpRequest) -> Any:
        """Execute the request safely, ignoring some errors.

        :param request: the request to execute
        :type request: googleapiclient.http.HttpRequest
        :return: the response
        :rtype: Any
        """

        count = 0
        limit = 5
        while count < limit:
            try:
                response = request.execute()
                return response
            except (BrokenPipeError, IOError) as error:
                LOGGER.exception(
                    "There was an error with executing the request!")
                count += 1
                if count >= limit:
                    raise IOError from error
                LOGGER.debug("Continuing in 60...")
                time.sleep(60)

        # Catch-all
        return Exception("Request failed after 5 retries.")

    @func_set_timeout(AUTHORISATION_TIMEOUT)
    def pushbullet_request_response(self, title: str, url: str) -> str:
        """Pushes the URL to Pushbullet and awaits a response

        This pushes the given URL to Pushbullet using the config. It will
        catch any Pushbullet-associated exceptions.

        :param title: the title of the URL
        :type title: str
        :param url: the URL to push
        :type url: str
        :return: the response text
        :rtype: str
        """

        # Attempt to authenticate
        try:
            LOGGER.debug("Authenticating with Pushbullet")
            pb = Pushbullet(self.config["pushbullet_access_token"])
            LOGGER.debug("Authenticated with Pushbullet.")
        except InvalidKeyError:
            LOGGER.exception(
                "InvalidKeyError raised when authenticating Pushbullet.")
            traceback.print_exc()

        # If successfully authenticated then attempt to push
        else:
            try:

                # Push to the device(s)
                if str(self.config["pushbullet_device"]).lower() == "false":
                    pb.get_device(str(self.config["pushbullet_device"])).push_link(
                        title, url)
                    LOGGER.debug("Pushed URL %s with title %s to all devices.",
                                 url, title)
                else:
                    pb.push_link(title, url)
                    LOGGER.debug("Pushed URL %s with title %s to device %s.",
                                 url, title, self.config["pushbullet_device"])

                # Get the response
                callback_start = str(datetime.now(tz=TIMEZONE).timestamp())
                while True:
                    pushes = pb.get_pushes(modified_after=callback_start)
                    LOGGER.debug("Pushes is: \n%s.", str(pushes))
                    if len(pushes) > 0 and "body" in pushes[0].keys():
                        pb.dismiss_push(pushes[0]["iden"])
                        return pushes[0]["body"]
                    time.sleep(5)

            except InvalidKeyError:
                LOGGER.exception(
                    "InvalidKeyError raised when using Pushbullet.")
                traceback.print_exc()
            except PushError:
                LOGGER.exception("PushError raised when using Pushbullet.")
                traceback.print_exc()

    def list_all_playlists(self) -> List[yt_types.YouTubePlaylist]:
        """Fetch all the playlists.

        :return: the playlists
        :rtype: list[yt_types.YouTubePlaylist]
        """

        LOGGER.debug("Fetching all the playlists...")
        next_page_token = ""
        all_playlists = []
        while next_page_token is not None:
            response: yt_types.YouTubePlaylistList = self.execute_request(
                self.get_service().playlists().list(
                    part="id,snippet",
                    mine=True,
                    maxResults=50,
                    pageToken=next_page_token))
            LOGGER.debug("Response is: \n%s.",
                         json.dumps(response, indent=4))
            all_playlists.extend(response["items"])
            next_page_token = response.get("nextPageToken")
        LOGGER.debug("Playlists is: \n%s.",
                     json.dumps(all_playlists, indent=4))

        return all_playlists

    def add_to_playlist(self, video_id: str, playlist_id: str) -> None:
        """Add the video to the playlist.

        :param video_id: the ID of the video to add
        :type video_id: str
        :param playlist_id: the ID of the playlist to add to
        :type playlist_id: str
        """

        LOGGER.info("Adding the video to the playlist...")
        LOGGER.info(locals())

        # Add the video to the playlist
        playlist_item: yt_types.YouTubePlaylistItem = self.execute_request(
            self.get_service().playlistItems().insert(
                part="id,snippet",
                body={
                    "snippet": {
                        "playlistId": playlist_id,
                        "resourceId": {
                            "videoId": video_id,
                            "kind": "youtube#video"}}}))
        LOGGER.debug(
            "Playlist Item is: \n%s.",
            json.dumps(
                playlist_item,
                indent=4))

        LOGGER.info("Added the video to the playlist successfully!")

    def delete_from_playlist(self, video_id: str, playlist_id: str) -> None:
        """Delete all occurrences of the video from the playlist.

        :param video_id: the ID of the video to delete
        :type video_id: str
        :param playlist_id: the ID of the playlist to delete from
        :type playlist_id: str
        """

        LOGGER.info("Deleting the video from the playlist...")
        LOGGER.info(locals())

        # List all the playlist items
        next_page_token = ""
        all_playlist_items = []
        while next_page_token is not None:
            response: yt_types.YouTubePlaylistItemList = self.execute_request(
                self.get_service().playlistItems().list(
                    part="id,snippet",
                    playlistId=playlist_id,
                    maxResults=50,
                    pageToken=next_page_token))
            LOGGER.debug("Response is: \n%s.", json.dumps(response, indent=4))
            all_playlist_items.extend(response["items"])
            next_page_token = response.get("nextPageToken")

        # Get a list of item IDs to delete
        item_ids = [item["id"] for item in all_playlist_items if item["snippet"]["resourceId"]["videoId"] == video_id]
        LOGGER.debug("Item IDs is: \n%s.", json.dumps(item_ids, indent=4))

        # Delete the items from the playlist
        for item_id in item_ids:
            self.execute_request(self.get_service().playlistItems().delete(id=item_id))
            LOGGER.debug("Deleted item with ID %s.", item_id)

        LOGGER.info("Deleted the video from the playlist successfully!")


class BroadcastTypes(Enum):
    """The possible types for a broadcast, including an 'all' type."""

    SCHEDULED = auto()
    LIVE = auto()
    FINISHED = auto()
    ALL = auto()


class YouTubeLivestream(YouTube):
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
