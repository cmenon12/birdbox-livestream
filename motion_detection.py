import argparse
import configparser
import email
import email.utils
import json
import logging
import os
import re
import smtplib
import ssl
import time
import traceback
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path
from typing import List

import dvr_scan
import googleapiclient
import humanize
import send2trash
import yt_dlp
from googleapiclient.discovery import build
from pytz import timezone

import google_services
import yt_livestream
import yt_types

__author__ = "Christopher Menon"
__credits__ = "Christopher Menon"
__license__ = "gpl-3.0"

# The name of the config file
CONFIG_FILENAME = "config.ini"

# The timezone to use throughout
TIMEZONE = timezone("Europe/London")

# All the motion detection parameters
MOTION_DETECTION_PARAMS = {
    "min_event_len": 30 * 3,
    "time_pre_event": "0s",
    "time_post_event": "0s",
    "roi": [33, 37, 145, 84],
    # Rectangle of form [x y w h] representing bounding box of subset of each frame to look at
    "threshold": 0.5  # the threshold for motion 0 < t < 1, default 0.15
}


def get_complete_broadcasts(
        service: googleapiclient.discovery.Resource) -> List[yt_types.YouTubeLiveBroadcast]:
    """Get a list of all complete broadcasts.

    :param service: the YouTube API service
    :type service: googleapiclient.discovery.Resource
    :return: a list of complete broadcasts
    :rtype: yt_types.YouTubeLiveBroadcast
    """

    LOGGER.info("Fetching the complete broadcasts...")
    next_page_token = ""
    all_broadcasts = []
    while next_page_token is not None:
        response: yt_types.YouTubeLiveBroadcastList = yt_livestream.YouTubeLivestream.execute_request(
            service.liveBroadcasts().list(
                part="id,snippet,status",
                mine=True,
                maxResults=50,
                pageToken=next_page_token))
        LOGGER.debug("Response is: \n%s.", json.dumps(response, indent=4))
        all_broadcasts.extend(response["items"])
        next_page_token = response.get("nextPageToken")
    LOGGER.debug(
        "all_broadcasts is: \n%s.",
        json.dumps(
            all_broadcasts,
            indent=4))

    # Collate the complete broadcasts
    complete_broadcasts = []
    for item in all_broadcasts:
        if item["status"]["lifeCycleStatus"] == "complete":
            complete_broadcasts.append(item)
    LOGGER.debug("complete_broadcasts is: %s.", complete_broadcasts)

    LOGGER.info("Complete broadcasts fetched successfully!")
    return complete_broadcasts


def download_video(video_id: str) -> str:
    """Download the low-res YouTube video and return the filename.

    :param video_id: the ID of the video to download
    :type video_id: str
    :return: the filename of the downloaded video
    :rtype: str
    """

    LOGGER.info("Downloading video...")
    LOGGER.info(locals())
    ydl_opts = {
        "format": "160",
        "final_ext": "mp4",
        "throttledratelimit": 10000
    }
    yt_dlp.utils.std_headers.update({"Referer": "https://www.google.com"})
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        ydl.download(f"https://youtu.be/{video_id}")
        filename = ydl.extract_info(
            f"https://youtu.be/{video_id}")["requested_downloads"][0]["_filename"]
    LOGGER.debug("Video filename is %s.", filename)
    LOGGER.info("Video downloaded successfully!")
    return filename


def get_motion_timestamps(filename: str) -> str:
    """Detect motion and output a description of when it occurs.

    :param filename: the video file to search
    :type filename: str
    :return: a description of the motion detected
    :rtype: str
    """

    LOGGER.info("Detecting motion...")
    LOGGER.info(locals())
    output = ""
    scan = dvr_scan.scanner.ScanContext([filename])
    scan.set_event_params(
        min_event_len=MOTION_DETECTION_PARAMS["min_event_len"],
        time_pre_event=MOTION_DETECTION_PARAMS["time_pre_event"],
        time_post_event=MOTION_DETECTION_PARAMS["time_post_event"]
    )
    scan.set_detection_params(
        roi=MOTION_DETECTION_PARAMS["roi"],
        threshold=MOTION_DETECTION_PARAMS["threshold"]
    )
    result = scan.scan_motion()
    if len(result) == 0:
        output = "No motion was detected in this video 😢."
    elif len(result) == 1:
        output = "\n\nMotion was detected at "
        duration = int(result[0][1].get_seconds() - result[0][0].get_seconds())
        output += f"{result[0][0].get_timecode(0)} for {duration} second{'s' if duration != 1 else ''}.\n"
    else:
        output = "\n\nMotion was detected at the following points:\n"
        for item in result:
            duration = int(item[1].get_seconds() - item[0].get_seconds())
            output += f" • {item[0].get_timecode(0)} for {duration} second{'s' if duration != 1 else ''}.\n"
    output += f"\n\nMOTION_DETECTION_PARAMS={MOTION_DETECTION_PARAMS}"
    LOGGER.debug("Output is: \n%s.", output)

    LOGGER.info("Motion detected successfully!")
    return output


def update_motion_status(
        service: googleapiclient.discovery.Resource,
        video_id: str,
        motion_desc: str) -> None:
    """Update the video with motion information.

    :param service: the YouTube API service
    :type service: googleapiclient.discovery.Resource
    :param video_id: the ID of the video to update
    :type video_id: str
    :param motion_desc: a description of the motion detected
    :type motion_desc: str
    """

    LOGGER.info("Appending to the video description...")
    LOGGER.info(locals())

    # Get the existing snippet details
    videos: yt_types.YouTubeVideoList = yt_livestream.YouTubeLivestream.execute_request(
        service.videos().list(id=video_id, part="id,snippet"))
    LOGGER.debug("Videos is: \n%s.", json.dumps(videos, indent=4))

    # Prepare a new title
    if "No motion" in motion_desc:
        title = f"{videos['items'][0]['snippet']['title']} (no motion)"
    else:
        count = motion_desc.count(" for ")
        if count == 1:
            title = f"{videos['items'][0]['snippet']['title']} ({count} action)"
        else:
            title = f"{videos['items'][0]['snippet']['title']} ({count} actions)"

    # Prepare the body
    body = {"id": video_id, "snippet": {}}
    body["snippet"]["categoryId"] = videos["items"][0]["snippet"]["categoryId"]
    body["snippet"]["tags"] = videos["items"][0]["snippet"].get("tags", [])
    body["snippet"]["description"] = f"{videos['items'][0]['snippet']['description']} {motion_desc}"
    body["snippet"]["title"] = title
    body["snippet"]["defaultLanguage"] = videos["items"][0]["snippet"]["defaultLanguage"]

    LOGGER.debug("Body is: \n%s.", body)

    # Update it
    LOGGER.debug("Updating the video metadata...")
    video: yt_types.YouTubeVideo = yt_livestream.YouTubeLivestream.execute_request(
        service.videos().update(part="id,snippet", body=body))
    LOGGER.debug("Video is: \n%s.", json.dumps(video, indent=4))

    LOGGER.info("Video description appended to successfully!")


def send_motion_email(
        config: configparser.SectionProxy,
        video_id: str,
        motion_desc: str) -> None:
    """Send an email about the motion that was detected.

    :param config: the config to use
    :type config: configparser.SectionProxy
    :param video_id: the ID of the video
    :type video_id: str
    :param motion_desc: a description of the motion detected
    :type motion_desc: str
    """

    LOGGER.info("Sending the motion email...")

    # Create the message
    message = MIMEMultipart("alternative")
    message["Subject"] = "Motion detected in the birdbox!"
    message["To"] = config["to"]
    message["From"] = config["from"]
    message["Date"] = email.utils.formatdate()
    email_id = email.utils.make_msgid(domain=config["smtp_host"])
    message["Message-ID"] = email_id

    # Create and attach the text
    text = f"We found some motion in this video: https://youtu.be/{video_id} {motion_desc}" \
           f"\n\n———\nThis email was sent automatically by a computer program (" \
           f"https://github.com/cmenon12/birdbox-livestream). "
    message.attach(MIMEText(text, "plain"))

    LOGGER.debug("Message is: \n%s.", message)

    # Create the SMTP connection and send the email
    with smtplib.SMTP_SSL(config["smtp_host"],
                          int(config["smtp_port"]),
                          context=ssl.create_default_context()) as server:
        server.login(config["username"], config["password"])
        server.sendmail(re.findall("(?<=<)\\S+(?=>)", config["from"])[0],
                        re.findall("(?<=<)\\S+(?=>)", config["to"]),
                        message.as_string())

    LOGGER.info("Motion email sent successfully!\n")


def main():
    """Runs the motion detection script indefinitely."""

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
    motion_config = parser["motion_detection"]

    # Save the directories
    old_cwd = os.getcwd()
    download_folder = Path(motion_config["download_folder"]) if \
        motion_config["download_folder"] != "" else Path(os.getcwd())

    try:

        # Get initial access to the YouTube API
        yt = google_services.YouTube(yt_config)
        yt.get_service()

        all_done = False
        while True:

            # Find out which videos need processing
            new_ids = []
            new_complete_broadcasts = get_complete_broadcasts(yt.get_service())
            for video in new_complete_broadcasts:
                if "motion" not in video["snippet"]["description"].lower() and \
                        video["status"]["privacyStatus"] != "private":
                    new_ids.append(video["id"])
            new_ids.reverse()
            LOGGER.debug("new_ids is: %s.", new_ids)

            # Tell the user if they're all done
            if new_ids == [] and all_done is False:
                print("No new videos to process!")
                all_done = True
            elif new_ids != [] and all_done is True:
                all_done = False

            # Process them
            for video_id in new_ids:
                print(f"{'Downloading' if args.download_only else 'Processing'} {video_id}...")

                # Try to download the video, but just skip for now if it fails
                try:
                    os.chdir(download_folder)
                    LOGGER.debug("Changed working directory to %s.", os.getcwd())
                    filename = download_video(video_id)
                    os.chdir(old_cwd)
                    LOGGER.debug("Changed working directory to %s.", os.getcwd())
                    filename = str(download_folder / filename)
                    LOGGER.debug("filename is: %s.", filename)
                except (yt_dlp.utils.DownloadError, yt_dlp.utils.ExtractorError) as error:
                    LOGGER.exception(
                        "There was an error with downloading the video!")
                    print("There was an error with downloading the video!")
                    print(f"{traceback.format_exc()}\n")
                    os.chdir(old_cwd)
                    LOGGER.debug("Changed working directory to %s.", os.getcwd())

                    # Record no motion if the recording is unavailable
                    if "This live stream recording is not available." in error.msg:
                        update_motion_status(yt.get_service(), video_id,
                                             "No motion was detected in this video as the recording is not available 😢.")
                        print("Marked the video as having no motion.")

                    continue
                else:
                    LOGGER.debug(
                        "%s is %s big.",
                        filename,
                        humanize.naturalsize(
                            os.path.getsize(filename)))

                    if not args.download_only:

                        # Run motion detection
                        motion_desc = get_motion_timestamps(filename)
                        update_motion_status(
                            yt.get_service(), video_id, motion_desc)
                        if "No motion" not in motion_desc:
                            send_motion_email(email_config, video_id, motion_desc)
                            yt.add_to_playlist(video_id, yt_config["motion_playlist_id"])
                        else:
                            try:
                                send2trash.send2trash(filename)
                            except send2trash.TrashPermissionError as error:
                                LOGGER.exception("Could not delete %s!", filename)
                                print(f"Could not delete {filename}!")
                                print(str(error))
                                print(traceback.format_exc())

                    print(f"{'Downloaded' if args.download_only else 'Processed'} {video_id} successfully!\n")

            # Wait before repeating
            time.sleep(15 * 60)

    except Exception as error:
        LOGGER.error("\n\n")
        LOGGER.exception("There was an exception!!")
        os.chdir(old_cwd)
        LOGGER.debug("Changed working directory to %s.", os.getcwd())
        yt_livestream.send_error_email(
            email_config, traceback.format_exc(), log_filename)
        raise Exception from error


if __name__ == "__main__":

    # Prepare the log
    Path("./logs").mkdir(parents=True, exist_ok=True)
    log_filename = f"birdbox-livestream-motion-detection-{datetime.now(tz=TIMEZONE).strftime('%Y-%m-%d %H-%M-%S %Z')}.txt"
    log_format = "%(asctime)s | %(levelname)5s in %(module)s.%(funcName)s() on line %(lineno)-3d | %(message)s"
    log_handler = logging.FileHandler(
        f"./logs/{log_filename}", mode="a", encoding="utf-8")
    log_handler.setFormatter(logging.Formatter(log_format))
    logging.basicConfig(
        format=log_format,
        level=logging.DEBUG,
        handlers=[log_handler])
    LOGGER = logging.getLogger(__name__)

    # Parse the args
    parser = argparse.ArgumentParser()
    parser.add_argument("-d", "--download-only", action="store_true")
    args = parser.parse_args()
    LOGGER.info("Args are: %s.", args)

    # Run it
    main()

else:
    LOGGER = logging.getLogger(__name__)
