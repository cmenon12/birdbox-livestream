import configparser
import json
import logging
import os
import pickle
import time
import traceback
from datetime import datetime
from enum import Enum, auto
from typing import Any, List, Optional

import google
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

# How long to wait for authorisation (in seconds)
AUTHORISATION_TIMEOUT = 600

# File with the OAuth client secret
CLIENT_SECRET_FILE = "client_secret.json"

# The timezone to use throughout
TIMEZONE = timezone("Europe/London")


class AuthorisationTypes(Enum):
    """The possible types for API authorisation"""

    SSH = auto()
    PUSHBULLET = auto()
    BROWSER = auto()


class GoogleService:
    """Represents a Google service API.

    :param config: the config to use
    :type config: configparser.SectionProxy
    :param service_name: the name of the service
    :type service_name: str
    :param service_version: the version of the service
    :type service_version: str
    :param scopes: the scopes to use
    :type scopes: List[str]
    :param token_file: the file to store the token in
    :type token_file: Optional[str]
    """

    def __init__(self, config: configparser.SectionProxy, service_name: str,
                 service_version: str, scopes: List[str], token_file: Optional[str] = None):

        self.config = config
        self.service_name = service_name
        self.service_version = service_version
        self.scopes = scopes
        self.token_file: str = token_file if token_file else f"{service_name}_{service_version}.pickle"

    @func_set_timeout(AUTHORISATION_TIMEOUT)
    def authorise_service(self, auth_type: AuthorisationTypes) -> googleapiclient.discovery.Resource:
        """Authorise the request.

        :param auth_type: how to authorise the request
        :type auth_type: AuthorisationTypes
        :return: the credentials
        :rtype: google.oauth2.credentials.Credentials
        """

        # Open the browser for the user to authorise it
        if auth_type is AuthorisationTypes.BROWSER:
            flow = InstalledAppFlow.from_client_secrets_file(
                CLIENT_SECRET_FILE, self.scopes)
            print("Your browser should open automatically.")
            return flow.run_local_server(port=0)

        # Tell the user to authorise it themselves
        else:
            flow = InstalledAppFlow.from_client_secrets_file(
                CLIENT_SECRET_FILE, self.scopes,
                redirect_uri="http://localhost:1/")
            auth_url, _ = flow.authorization_url(prompt="consent")
            print(
                f"Please visit this URL to authorise this application: {auth_url}")
            if auth_type is AuthorisationTypes.PUSHBULLET and str(
                    self.config["pushbullet_access_token"]).lower() != "false":
                print("Requesting via Pushbullet...")
                code = self.pushbullet_request_response(
                    "Google API Authorisation", auth_url)
            else:
                code = input("Enter the authorisation code: ")
            flow.fetch_token(code=code)
            return flow.credentials

    def get_service(self,
                    auth_type: AuthorisationTypes = AuthorisationTypes.PUSHBULLET) -> google.auth.credentials.Credentials:
        """Authenticates the API, returning the service.

        :return: the API service (a Resource)
        :rtype: google.auth.credentials.Credentials
        """

        LOGGER.info("Authorising service...")

        # Attempt to access pre-existing credentials
        if os.path.exists(self.token_file):
            with open(self.token_file, "rb") as token:
                LOGGER.debug("Loading credentials from %s.", self.token_file)
                credentials = pickle.load(token)

            # Try to refresh the credentials
            LOGGER.debug("Credentials are: %s.", str(credentials))
            try:
                credentials.refresh(Request())
            except RefreshError:
                os.remove(self.token_file)
                try:
                    credentials = self.authorise_service(auth_type)
                except FunctionTimedOut as error:
                    raise FunctionTimedOut(
                        f"Waited {AUTHORISATION_TIMEOUT} seconds to authorise Google API.") from error

        # If they don't exist then get some new ones
        else:
            try:
                credentials = self.authorise_service(auth_type)
            except FunctionTimedOut as error:
                raise FunctionTimedOut(
                    f"Waited {AUTHORISATION_TIMEOUT} seconds to authorise Google API.") from error

        # Save the credentials for the next run
        with open(self.token_file, "wb") as token:
            pickle.dump(credentials, token)
        LOGGER.debug("Credentials saved to %s successfully.",
                     self.token_file)

        # Create and return the authenticated service
        service = build(self.service_name, self.service_version, credentials=credentials)

        assert os.path.exists(self.token_file)

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


class YouTube(GoogleService):
    """Represents the YouTube API.

    :param config: the config to use
    :type config: configparser.SectionProxy
    """

    def __init__(self, config: configparser.SectionProxy, token_file: Optional[str] = None):

        super().__init__(config, "youtube", "v3", ["https://www.googleapis.com/auth/youtube"], token_file)

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


if __name__ != "__main__":
    LOGGER = logging.getLogger(__name__)
