import datetime
import os
import pickle

import googleapiclient
from google.auth.transport.requests import Request
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from pytz import timezone

__author__ = "Christopher Menon"
__credits__ = "Christopher Menon"
__license__ = "gpl-3.0"

# File with the OAuth client secret
CLIENT_SECRET_FILE = "client_secret.json"

# API-specific credentials
SCOPES = ["https://www.googleapis.com/auth/youtube"]
API_SERVICE_NAME = "youtube"
API_VERSION = "v3"

# File with the user's access and refresh tokens
TOKEN_PICKLE_FILE = "token.pickle"

# Must be public, unlisted, or private
PRIVACY_STATUS = "private"

# The timezone to use throughout
TIMEZONE = timezone("Europe/London")

# The default duration in minutes
DEFAULT_DURATION = 180


class YouTubeLivestream:

    def __init__(self, authorise: bool = True):
        if authorise is True:
            self.service = YouTubeLivestream.get_service()
        else:
            self.service = None

        self.liveStream = None
        self.liveBroadcasts = {}

    @staticmethod
    def get_service() -> googleapiclient.discovery.Resource:
        """Authenticates the YouTube API, returning the service.

        :return: the YouTube API service (a Resource)
        :rtype: googleapiclient.discovery.Resource
        """

        credentials = None

        # Attempt to access pre-existing credentials
        if os.path.exists(TOKEN_PICKLE_FILE):
            with open(TOKEN_PICKLE_FILE, "rb") as token:
                credentials = pickle.load(token)

        # If there are no (valid) credentials available let the user log in
        if not credentials or not credentials.valid:
            if credentials and credentials.expired and credentials.refresh_token:
                credentials.refresh(Request())
            else:
                flow = InstalledAppFlow.from_client_secrets_file(
                    CLIENT_SECRET_FILE, SCOPES)
                credentials = flow.run_local_server(port=0)

            # Save the credentials for the next run
            with open(TOKEN_PICKLE_FILE, "wb") as token:
                pickle.dump(credentials, token)

        # Create and return the authenticated service
        service = build("youtube", "v3", credentials=credentials)

        assert os.path.exists(TOKEN_PICKLE_FILE)

        return service

    def get_stream(self) -> dict:
        """Gets the liveStream, creating it if needed.

        :return: the YouTube liveStream resource
        :rtype: dict
        """

        # Return the existing stream
        if self.liveStream is not None:
            return self.liveStream

        # Create a new livestream
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
                    "title": "Birdbox Livestream"
                }
            }).execute()

        # Save and return it
        self.liveStream = stream
        return stream

    def create_broadcast(self, scheduledStartTime: datetime.datetime = datetime.datetime.now(tz=TIMEZONE),
                         duration_mins: int = DEFAULT_DURATION):
        """Creates the live broadcast.

        :param scheduledStartTime: when the broadcast should start
        :type scheduledStartTime: datetime.datetime, optional
        :param duration_mins: how long the broadcast will last for in minutes
        :type duration_mins: int, optional
        :return: the YouTube liveBroadcast resource
        :rtype: dict
        """

        # Stop if a broadcast already exists at this time
        if scheduledStartTime in self.liveBroadcasts.keys():
            return self.liveBroadcasts[scheduledStartTime]

        # Create a new broadcast
        broadcast = self.service.liveBroadcasts().insert(
            part="id,snippet,contentDetails,status",
            body={
                "contentDetails": {
                    "enableAutoStart": True,
                    "enableAutoStop": True,
                    "enableClosedCaptions": False,
                    "enableDvr": True,
                    "enableEmbed": True,
                    "recordFromStart": True,
                    "startWithSlate": False
                },
                "snippet": {
                    "scheduledStartTime": scheduledStartTime.isoformat(),
                    "scheduledEndTime": (scheduledStartTime + datetime.timedelta(minutes=duration_mins)).isoformat(),
                    "title": f"Birdbox Livestream on {scheduledStartTime.strftime('%a %d %b at %H:%M')}"
                },
                "status": {
                    "privacyStatus": PRIVACY_STATUS,
                    "selfDeclaredMadeForKids": False
                }
            }).execute()

        # Save and return it
        self.liveBroadcasts[scheduledStartTime] = broadcast
        return broadcast

    def start_broadcast(self, scheduledStartTime: datetime.datetime):
        """Start the broadcast by binding the stream to it.

        :param scheduledStartTime: when the broadcast should start
        :type scheduledStartTime: datetime.datetime, optional
        :return: the updated YouTube liveBroadcast resource
        :rtype: dict
        :raises ValueError: if the broadcast at that times doesn't exist
        """

        # Check that this broadcast exists.
        if scheduledStartTime not in self.liveBroadcasts.keys():
            raise ValueError(f"The broadcast at {scheduledStartTime.isoformat()} does not exist!")

        # Bind the broadcast to the stream
        broadcast = self.service.liveBroadcasts().bind(
            id=self.liveBroadcasts[scheduledStartTime]["id"],
            part="id,snippet,contentDetails,status",
            streamId=self.get_stream()["id"]
        ).execute()

        # Save and return it
        self.liveBroadcasts[scheduledStartTime] = broadcast
        return broadcast

    def end_broadcast(self, scheduledStartTime: datetime.datetime):
        """End the broadcast by changing it's state to complete.

        :param scheduledStartTime: when the broadcast should start
        :type scheduledStartTime: datetime.datetime, optional
        :return: the updated YouTube liveBroadcast resource
        :rtype: dict
        :raises ValueError: if the broadcast at that times doesn't exist
        """

        # Check that this broadcast exists
        if scheduledStartTime not in self.liveBroadcasts.keys():
            raise ValueError(f"The broadcast at {scheduledStartTime.isoformat()} does not exist!")

        # Change its status to complete
        broadcast = self.service.liveBroadcasts().transition(
            broadcastStatus="complete",
            id=self.liveBroadcasts[scheduledStartTime]["id"],
            part="id,snippet,contentDetails,status"
        ).execute()

        # Save and return the updated resource
        self.liveBroadcasts[scheduledStartTime] = broadcast
        return bound_broadcast

    def get_broadcasts(self):

        return self.liveBroadcasts


def main():
    yt = YouTubeLivestream()

    yt.get_stream()


if __name__ == "__main__":
    main()
