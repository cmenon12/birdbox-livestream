import configparser
import json
import logging
import sys
from datetime import datetime, date
from typing import List

from pick import pick
from pytz import timezone

__author__ = "Christopher Menon"
__credits__ = "Christopher Menon"
__license__ = "gpl-3.0"

from utilities import DatetimeFormat as DTFmt
import utilities
from yt_livestream import YouTubeLivestream
from yt_types import YouTubePlaylist, YouTubeLiveBroadcast

# The name of the config file
CONFIG_FILENAME = "config.ini"

# The timezone to use throughout
TIMEZONE = timezone("Europe/London")

# The filename to use for the log file
LOG_FILENAME = f"birdbox-livestream-yt-cleanup-{datetime.now(tz=TIMEZONE).strftime(DTFmt.datetime_fmt(time_sep='.'))}.txt"


def ask_yes_or_no():
    """Asks the user to confirm they want to continue."""

    answer = input("y/n: ")
    LOGGER.debug("User chose option %s.", answer)

    if answer != "y":
        LOGGER.debug("User chose not to continue, exiting.")
        sys.exit()


def update_no_motion_videos(yt: YouTubeLivestream, privacy: str,
                            start_date: date = None, end_date: date = None):
    """Delete or update the privacy of the specified weekly playlists.

    :param yt: the YouTube Livestream object
    :type yt: YouTubeLivestream
    :param start_date: the start date for videos
    :type start_date: date
    :param end_date: the end date for videos
    :type end_date: date
    :param privacy: the privacy status to set
    :type privacy: str
    """

    LOGGER.info("Updating videos...")
    LOGGER.debug(locals())

    # Download all videos
    videos: List[YouTubeLiveBroadcast] = []
    all_videos = yt.list_all_broadcasts(part="id,snippet,status", broadcast_status="completed")
    for video in all_videos:
        if "(no motion)" in video["snippet"]["title"]:
            video_date = yt.parse_scheduled_time(video["snippet"]["scheduledStartTime"]).date()
            if (start_date and video_date < start_date) or (end_date and video_date > end_date):
                continue
            if video["status"]["privacyStatus"] == privacy:
                continue
            videos.append(video)

    LOGGER.debug("Found %s videos in total.", len(videos))

    # Ask the user to confirm
    titles = [video["snippet"]["title"] for video in videos]
    print(
        f"Are you sure you want to {privacy.upper()} all these videos?\n{json.dumps(titles, indent=4)}")
    ask_yes_or_no()

    all_playlists = yt.list_all_playlists()

    for video in videos:

        if privacy == "delete":
            start_time = yt.parse_scheduled_time(video["snippet"]["scheduledStartTime"])
            yt.delete_broadcast(video["id"], start_time, all_playlists)
            LOGGER.debug("Deleted video %s %s.", video["id"], video["snippet"]["title"])
        else:
            body = {"id": video["id"], "status": {"privacyStatus": "private"}}
            yt.execute_request(yt.get_service().videos().update(
                part="id,status",
                body=body
            ))
            LOGGER.debug("Updated video %s %s.", video["id"], video["snippet"]["title"])

    LOGGER.info("Updated the videos successfully!")


def update_weekly_playlists(yt: YouTubeLivestream, privacy: str,
                            start_date: date = None, end_date: date = None):
    """Delete or update the privacy of the specified weekly playlists.

    :param yt: the YouTube Livestream object
    :type yt: YouTubeLivestream
    :param start_date: the start date for playlists
    :type start_date: date
    :param end_date: the end date for playlists
    :type end_date: date
    :param privacy: the privacy status to set
    :type privacy: str
    """

    LOGGER.info("Updating playlists...")
    LOGGER.debug(locals())

    # Download all playlists
    all_playlists = yt.list_all_playlists()
    playlists: List[YouTubePlaylist] = []
    for playlist in all_playlists:
        if ": w/c" in playlist["snippet"]["title"]:
            video_date = datetime.strptime(playlist["snippet"]["title"][-11:],
                                           DTFmt.pretty_date_fmt(day=False)).date()
            if (start_date and video_date < start_date) or (end_date and video_date > end_date):
                continue
            if playlist["status"]["privacyStatus"] == privacy:
                continue
            playlists.append(playlist)

    LOGGER.debug("Found %s playlists in total.", len(playlists))

    # Ask the user to confirm
    titles = [playlist["snippet"]["title"] for playlist in playlists]
    print(
        f"Are you sure you want to {privacy.upper()} all these playlists?\n{json.dumps(titles, indent=4)}")
    ask_yes_or_no()

    for playlist in playlists:

        if privacy == "delete":
            yt.execute_request(yt.get_service().playlists().delete(
                id=playlist["id"]
            ))
            LOGGER.debug("Deleted playlist %s %s.", playlist["id"], playlist["snippet"]["title"])
        else:
            body = {"id": playlist["id"], "status": {"privacyStatus": "private"},
                    "snippet": {"title": playlist["snippet"]["title"],
                                "description": playlist["snippet"]["description"]}}
            yt.execute_request(yt.get_service().playlists().update(
                part="id,status,snippet",
                body=body
            ))
            LOGGER.debug("Updated playlist %s %s.", playlist["id"], playlist["snippet"]["title"])

    LOGGER.info("Updated the playlists successfully!")


def main():
    """Run the script prompting the user to select an option."""

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
    start_date = datetime.strptime(start_date, DTFmt.date_fmt()).date() if start_date else None

    end_date = input("Enter the end date (YYYY-MM-DD): ")
    end_date = datetime.strptime(end_date, DTFmt.date_fmt()).date() if end_date else None

    if option == "make weekly playlists private":
        update_weekly_playlists(yt, "private", start_date, end_date)
    elif option == "delete weekly playlists":
        update_weekly_playlists(yt, "delete", start_date, end_date)
    elif option == "make no motion videos private":
        update_no_motion_videos(yt, "private", start_date, end_date)
    elif option == "delete no motion videos":
        update_no_motion_videos(yt, "delete", start_date, end_date)


if __name__ == "__main__":

    # Prepare the log
    LOGGER = utilities.prepare_logging(LOG_FILENAME)

    # Run it
    main()

else:
    LOGGER = logging.getLogger(__name__)
