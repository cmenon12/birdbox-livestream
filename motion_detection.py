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
from typing import Tuple, List

import dvr_scan
import googleapiclient
import humanize as humanize
import yt_dlp
from dvr_scan.timecode import FrameTimecode
from googleapiclient.discovery import build
from pytz import timezone

import yt_livestream

__author__ = "Christopher Menon"
__credits__ = "Christopher Menon"
__license__ = "gpl-3.0"

# The name of the config file
CONFIG_FILENAME = "config.ini"

# File with the list of completed IDs
SAVE_DATA_FILENAME = "save_data.json"

# The timezone to use throughout
TIMEZONE = timezone("Europe/London")

# The minimum length of the motion in seconds
MIN_MOTION_DURATION = 3


def get_complete_broadcasts(
        service: googleapiclient.discovery.Resource) -> List[str]:
    """Get a list of all complete broadcast IDs.

    :param service: the YouTube API service
    :type service: googleapiclient.discovery.Resource
    :return: a list of IDs of complete broadcasts
    :rtype: List[str]
    """

    LOGGER.info("Fetching the complete broadcasts...")
    next_page_token = ""
    all_broadcasts = []
    while next_page_token is not None:
        response = yt_livestream.YouTubeLivestream.execute_request(
            service.liveBroadcasts().list(
                part="id,status",
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
            complete_broadcasts.append(item["id"])
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
        "logger": LOGGER,
        "format": "best[height=144]+[ext=mp4]",
        "verbose": True,
        "final_ext": "mp4"
    }
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
        min_event_len=25 * MIN_MOTION_DURATION,
        time_pre_event="1s",
        time_post_event="0s")
    result: List[Tuple[FrameTimecode, FrameTimecode,
                       FrameTimecode]] = scan.scan_motion()
    if len(result) == 0:
        output = "No motion was detected in this video 😢."
    else:
        output = "\n\nMotion was detected at the following points:\n"
    for item in result:
        output += f" • {item[0].get_timecode(0)} for {humanize.naturaldelta(item[2].get_seconds())}.\n"
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
    video = yt_livestream.YouTubeLivestream.execute_request(
        service.videos().list(id=video_id, part="id,snippet"))
    LOGGER.debug("Video is: \n%s.", json.dumps(video, indent=4))

    # Prepare a new title
    if "No motion" in motion_desc:
        title = f"{video['items'][0]['snippet']['title']} (no motion)"
    else:
        count = motion_desc.count(" for ")
        if count == 1:
            title = f"{video['items'][0]['snippet']['title']} ({count} action)"
        else:
            title = f"{video['items'][0]['snippet']['title']} ({count} actions)"

    # Prepare the body
    body = {"id": video_id, "snippet": {}}
    body["snippet"]["categoryId"] = video["items"][0]["snippet"]["categoryId"]
    body["snippet"]["tags"] = video["items"][0]["snippet"]["tags"]
    body["snippet"]["description"] = f"{video['items'][0]['snippet']['description']} {motion_desc}"
    body["snippet"]["title"] = title
    body["snippet"]["defaultLanguage"] = video["items"][0]["snippet"]["defaultLanguage"]

    LOGGER.debug("Body is: \n%s.", body)

    # Update it
    LOGGER.debug("Updating the video metadata...")
    video = yt_livestream.YouTubeLivestream.execute_request(
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
    main_config = parser["yt_livestream"]
    email_config = parser["email"]

    try:

        # Get access to the YouTube API
        service = yt_livestream.YouTubeLivestream.get_service()

        # Try and load the list of completed IDs
        try:
            with open(SAVE_DATA_FILENAME, "r") as file:
                complete_broadcasts = json.load(file)
            LOGGER.info("Loaded save data %s", complete_broadcasts)
        except FileNotFoundError:
            LOGGER.info(
                "Could not find save data %s, using empty list.",
                SAVE_DATA_FILENAME)
            complete_broadcasts = []

        while True:

            # Find out which videos need processing
            new_ids = []
            new_complete_broadcasts = get_complete_broadcasts(service)
            for video_id in new_complete_broadcasts:
                if video_id not in complete_broadcasts:
                    new_ids.append(video_id)
            LOGGER.debug("new_ids is: %s.", new_ids)

            # Process them
            for video_id in new_ids:
                print(f"Processing {video_id}...")
                filename = download_video(video_id)
                LOGGER.debug(
                    "%s is %s big.",
                    filename,
                    humanize.naturalsize(
                        os.path.getsize(filename)))
                motion_desc = get_motion_timestamps(filename)
                update_motion_status(service, video_id, motion_desc)
                os.remove(filename)
                if "No motion" not in motion_desc:
                    send_motion_email(email_config, video_id, motion_desc)
                print(f"Processed {video_id} successfully!\n")

                # Save the ID, as soon as it's done
                complete_broadcasts.append(video_id)
                with open(SAVE_DATA_FILENAME, "w") as file:
                    json.dump(complete_broadcasts, file)
                    LOGGER.debug(
                        "Saved the save data to %s successfully.",
                        SAVE_DATA_FILENAME)
                    LOGGER.debug("Saved save data is %s", complete_broadcasts)

            # Wait before repeating
            time.sleep(15 * 60)

    except Exception as error:
        LOGGER.error("\n\n")
        LOGGER.exception("There was an exception!!")
        yt_livestream.send_error_email(
            email_config, traceback.format_exc(), log_filename)
        raise Exception from error


if __name__ == "__main__":

    # Prepare the log
    Path("./logs").mkdir(parents=True, exist_ok=True)
    log_filename = f"birdbox-livestream-{datetime.now(tz=TIMEZONE).strftime('%Y-%m-%d %H-%M-%S %Z')}.txt"
    log_format = "%(asctime)s | %(levelname)5s in %(module)s.%(funcName)s() on line %(lineno)-3d | %(message)s"
    log_handler = logging.FileHandler(f"./logs/{log_filename}", mode="a", encoding="utf-8")
    log_handler.setFormatter(logging.Formatter(log_format))
    logging.basicConfig(
        format=log_format,
        level=logging.DEBUG,
        handlers=[log_handler])
    LOGGER = logging.getLogger(__name__)

    # Run it
    main()

else:
    LOGGER = logging.getLogger(__name__)
