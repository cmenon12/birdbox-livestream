import os
import pickle
from datetime import datetime, timedelta
from enum import Enum, auto

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

# The max number of broadcasts to schedule in advance
MAX_SCHEDULED_BROADCASTS = 3

# The command to start streaming, just add the RTMP address on the end
COMMAND = "raspivid -t 0 -w 1280 -h 720 -fps 25 -n -br 60 -co 10 -sh 70 -sa -100 -l -o - -a 1548 -ae 22 -ISO 600 -b " \
          "2000000 | ffmpeg -re -ar 44100 -ac 2 -acodec pcm_s16le -f s16le -ac 2 -i /dev/zero -f h264 -i - -vcodec " \
          "copy -acodec aac -ab 128k -g 50 -strict experimental -f flv -b:v 2000k -b:a 1k -maxrate 2000k -bufsize " \
          "1000k -preset veryfast "


class BroadcastTypes(Enum):
    SCHEDULED = auto()
    LIVE = auto()
    FINISHED = auto()
    ALL = auto()


class YouTubeLivestream:

    def __init__(self, authorise: bool = True):
        if authorise is True:
            self.service = YouTubeLivestream.get_service()
        else:
            self.service = None

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
                    "title": f"Birdbox Livestream at {datetime.now(tz=TIMEZONE).isoformat()}"
                }
            }).execute()

        # Save and return it
        self.liveStream = stream
        return stream

    def create_broadcast(self, scheduledStartTime: datetime.datetime = datetime.datetime.now(tz=TIMEZONE),
                         duration_mins: int = DEFAULT_DURATION):
        """Creates the live broadcast.

        :param start_time: when the broadcast should start
        :type start_time: datetime.datetime, optional
        :param duration_mins: how long the broadcast will last for in minutes
        :type duration_mins: int, optional
        :return: the YouTube liveBroadcast resource
        :rtype: dict
        """

        # Stop if a broadcast already exists at this time
        if start_time in self.get_broadcasts().keys():
            return self.get_broadcasts()[start_time]

        # Round the end time to the nearest hour
        end_time = start_time + timedelta(minutes=duration_mins)
        end_time = end_time.replace(second=0, microsecond=0, minute=0,
                                    hour=end_time.hour) + timedelta(
            hours=end_time.minute // 30)

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
                    "scheduledStartTime": start_time.isoformat(),
                    "scheduledEndTime": end_time.isoformat(),
                    "title": f"Birdbox Livestream on {start_time.strftime('%a %d %b at %H:%M')}"
                },
                "status": {
                    "privacyStatus": PRIVACY_STATUS,
                    "selfDeclaredMadeForKids": False
                }
            }).execute()

        # Save and return it
        self.scheduled_broadcasts[start_time] = broadcast
        print(f"Created a broadcast at {start_time.isoformat()} till {end_time.isoformat()}")
        return broadcast

    def start_broadcast(self, start_time: datetime):
        """Start the broadcast by binding the stream to it.

        :param start_time: when the broadcast should start
        :type start_time: datetime.datetime, optional
        :return: the updated YouTube liveBroadcast resource
        :rtype: dict
        :raises ValueError: if the broadcast at that times doesn't exist
        """

        # Check that this broadcast exists.
        if start_time not in self.scheduled_broadcasts.keys():
            raise ValueError(f"The broadcast at {start_time.isoformat()} is not scheduled!")

        # Bind the broadcast to the stream
        broadcast = self.service.liveBroadcasts().bind(
            id=self.scheduled_broadcasts[start_time]["id"],
            part="id,snippet,contentDetails,status",
            streamId=self.get_stream()["id"]
        ).execute()

        # Save and return it
        self.live_broadcasts[start_time] = broadcast
        self.scheduled_broadcasts.pop(start_time)
        print(f"Started a broadcast at {start_time.isoformat()}")
        return broadcast

    def end_broadcast(self, start_time: datetime):
        """End the broadcast by changing it's state to complete.

        :param start_time: when the broadcast should start
        :type start_time: datetime.datetime, optional
        :return: the updated YouTube liveBroadcast resource
        :rtype: dict
        :raises ValueError: if the broadcast at that times doesn't exist
        """

        # Check that this broadcast exists
        if start_time not in self.live_broadcasts.keys():
            raise ValueError(f"The broadcast at {start_time.isoformat()} is not live!")

        # Change its status to complete
        broadcast = self.service.liveBroadcasts().transition(
            broadcastStatus="complete",
            id=self.live_broadcasts[start_time]["id"],
            part="id,snippet,contentDetails,status"
        ).execute()

        # Save and return the updated resource
        self.finished_broadcasts[start_time] = broadcast
        self.live_broadcasts.pop(start_time)
        print(f"Ended a broadcast that started at {start_time.isoformat()}")
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
    yt = YouTubeLivestream()

    yt.get_stream()


if __name__ == "__main__":
    main()
