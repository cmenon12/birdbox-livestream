import configparser
import json
import logging
import sys
from datetime import datetime
from typing import List

from pick import pick
from pytz import timezone

__author__ = "Christopher Menon"
__credits__ = "Christopher Menon"
__license__ = "gpl-3.0"

import utilities
from yt_livestream import YouTubeLivestream
from yt_types import YouTubePlaylist, YouTubeLiveBroadcast

# The name of the config file
CONFIG_FILENAME = "config.ini"

# The timezone to use throughout
TIMEZONE = timezone("Europe/London")

# The filename to use for the log file
LOG_FILENAME = f"birdbox-livestream-yt-livestream-{datetime.now(tz=TIMEZONE).strftime('%Y-%m-%d %H-%M-%S %Z')}.txt"


def update_no_motion_videos(yt: YouTubeLivestream, start_date: datetime = None, end_date: datetime = None,
                            delete: bool = False, privacy: str = "private"):
    LOGGER.info("Updating videos...")
    LOGGER.info(locals())

    # Download all videos
    videos: List[YouTubeLiveBroadcast] = []
    next_page_token = ""
    while next_page_token is not None:
        response = yt.execute_request(yt.get_service().liveBroadcasts().list(
            part="id,snippet,status",
            broadcastStatus="completed",
            mine=True,
            maxResults=50,
            pageToken=next_page_token
        ))

        # Save the playlists we want to process
        LOGGER.debug("Found %s new videos.", len(response["items"]))
        for video in response["items"]:
            if "(no motion)" in video["snippet"]["title"]:
                date = datetime.strptime(video["snippet"]["scheduledStartTime"], "%Y-%m-%dT%H:%M:%SZ")
                if (start_date and date < start_date) or (end_date and date > end_date):
                    continue
                if not delete and video["status"]["privacyStatus"] == privacy:
                    continue
                videos.append(video)

        next_page_token = response.get("nextPageToken")

    LOGGER.debug("Found %s videos in total.", len(videos))

    # Ask the user to confirm
    titles = [video["snippet"]["title"] for video in videos]
    print(
        f"Are you sure you want to {'delete' if delete else privacy} all these videos?\n{json.dumps(titles, indent=4)}")
    answer = input("y/n: ")
    LOGGER.info("User chose option %s.", answer)

    if answer != "y":
        LOGGER.info("User chose not to continue, exiting.")
        sys.exit()

    all_playlists = yt.list_all_playlists()

    for video in videos:

        if delete is True:
            start_time = datetime.strptime(video["snippet"]["scheduledStartTime"], "%Y-%m-%dT%H:%M:%SZ")
            yt.delete_broadcast(video["id"], start_time, all_playlists)
            r = yt.execute_request(yt.get_service().videos().delete(
                id=video["id"]
            ))
            LOGGER.debug("Deleted video %s %s.", video["id"], video["snippet"]["title"])
        else:
            body = {"id": video["id"], "status": {"privacyStatus": "private"}}
            r = yt.execute_request(yt.get_service().videos().update(
                part="id,status",
                body=body
            ))
            LOGGER.debug("Updated video %s %s.", video["id"], video["snippet"]["title"])

    LOGGER.info("Updated the videos successfully!")


def update_weekly_playlists(yt: YouTubeLivestream, start_date: datetime = None, end_date: datetime = None,
                            delete: bool = False, privacy: str = "private"):
    LOGGER.info("Updating playlists...")
    LOGGER.info(locals())

    # Download all playlists
    playlists: List[YouTubePlaylist] = []
    next_page_token = ""
    while next_page_token is not None:
        response = yt.execute_request(yt.get_service().playlists().list(
            part="id,snippet,status",
            mine=True,
            maxResults=50,
            pageToken=next_page_token
        ))

        # Save the playlists we want to process
        LOGGER.debug("Found %s new playlists.", len(response["items"]))
        for playlist in response["items"]:
            if ": w/c" in playlist["snippet"]["title"]:
                date = datetime.strptime(playlist["snippet"]["title"][-11:], "%d %b %Y")
                if (start_date and date < start_date) or (end_date and date > end_date):
                    continue
                if not delete and playlist["status"]["privacyStatus"] == privacy:
                    continue
                playlists.append(playlist)

        next_page_token = response.get("nextPageToken")

    LOGGER.debug("Found %s playlists in total.", len(playlists))

    # Ask the user to confirm
    titles = [playlist["snippet"]["title"] for playlist in playlists]
    print(
        f"Are you sure you want to {'delete' if delete else privacy} all these playlists?\n{json.dumps(titles, indent=4)}")
    answer = input("y/n: ")
    LOGGER.info("User chose option %s.", answer)

    if answer != "y":
        LOGGER.info("User chose not to continue, exiting.")
        sys.exit()

    for playlist in playlists:

        if delete is True:
            r = yt.execute_request(yt.get_service().playlists().delete(
                id=playlist["id"]
            ))
            LOGGER.debug("Deleted playlist %s %s.", playlist["id"], playlist["snippet"]["title"])
        else:
            body = {"id": playlist["id"], "status": {"privacyStatus": "private"},
                    "snippet": {"title": playlist["snippet"]["title"],
                                "description": playlist["snippet"]["description"]}}
            r = yt.execute_request(yt.get_service().playlists().update(
                part="id,status,snippet",
                body=body
            ))
            LOGGER.debug("Updated playlist %s %s.", playlist["id"], playlist["snippet"]["title"])

    LOGGER.info("Updated the playlists successfully!")


def main():
    # Get the config
    parser = utilities.load_config(CONFIG_FILENAME)
    yt_config: configparser.SectionProxy = parser["YouTubeLivestream"]

    yt = YouTubeLivestream(yt_config)

    title = "What do you want to do?"
    options = ["make weekly playlists private", "delete weekly playlists",
               "make no motion videos private", "delete no motion videos"]
    option, _ = pick(options, title)
    LOGGER.info("User chose option %s.", option)

    start_date = input("Enter the start date (YYYY-MM-DD): ")
    start_date = datetime.strptime(start_date, "%Y-%m-%d") if start_date else None

    end_date = input("Enter the end date (YYYY-MM-DD): ")
    end_date = datetime.strptime(end_date, "%Y-%m-%d") if end_date else None

    if option == "make weekly playlists private":
        update_weekly_playlists(yt, start_date, end_date, delete=False, privacy="private")
    elif option == "delete weekly playlists":
        update_weekly_playlists(yt, start_date, end_date, delete=True)
    elif option == "make no motion videos private":
        update_no_motion_videos(yt, start_date, end_date, delete=False, privacy="private")
    elif option == "delete no motion videos":
        update_no_motion_videos(yt, start_date, end_date, delete=True)



if __name__ == "__main__":

    # Prepare the log
    LOGGER = utilities.prepare_logging(LOG_FILENAME)
    LOGGER.addHandler(logging.StreamHandler(sys.stdout))

    # Run it
    main()

else:
    LOGGER = logging.getLogger(__name__)
