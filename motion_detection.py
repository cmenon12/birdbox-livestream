import argparse
import configparser
import email
import email.utils
import json
import logging
import os
import time
import traceback
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path
from typing import List, Dict, Union

import dvr_scan
import googleapiclient
import html2text
import humanize
import send2trash
import yt_dlp
from jinja2 import Template
from pytz import timezone

import google_services
import utilities
import yt_livestream
import yt_types

__author__ = "Christopher Menon"
__credits__ = "Christopher Menon"
__license__ = "gpl-3.0"

# The name of the config file
CONFIG_FILENAME = "config.ini"

# The timezone to use throughout
TIMEZONE = timezone("Europe/London")

# The filename to use for the log file
LOG_FILENAME = f"birdbox-livestream-motion-detection-{datetime.now(tz=TIMEZONE).strftime('%Y-%m-%d %H-%M-%S %Z')}.txt"

# All the motion detection parameters
MOTION_DETECTION_PARAMS = {
    "min_event_len": 30 * 3,
    "time_pre_event": "0s",
    "time_post_event": "0s",
    "roi": [33, 37, 145, 84],
    # Rectangle of form [x y w h] representing bounding box of subset of each frame to look at
    "threshold": 0.5  # the threshold for motion 0 < t < 1, default 0.15
}


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


def get_motion_timestamps(filename: str) -> List[Dict[str, str]]:
    """Detect motion and return a list of motion events.

    :param filename: the video file to search
    :type filename: str
    :return: a list of motion events
    :rtype: List[Dict[str, str]]
    """

    LOGGER.info("Detecting motion...")
    LOGGER.info(locals())
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
    motion = scan.scan_motion()
    result = []
    for event in motion:
        result.append({"start": event[0].get_timecode(0),
                       "duration": int(event[1].get_seconds() - event[0].get_seconds())})

    LOGGER.debug("Motion result is: \n%s.", json.dumps(result, indent=4))

    LOGGER.info("Motion detected successfully!")
    return result


def update_motion_status(
        service: googleapiclient.discovery.Resource,
        video_id: str,
        motion: Union[List[Dict[str, str]], Dict[str, str]]) -> None:
    """Update the video with motion information.

    :param service: the YouTube API service
    :type service: googleapiclient.discovery.Resource
    :param video_id: the ID of the video to update
    :type video_id: str
    :param motion: a list of motion events or description & suffix
    :type motion: Union[List[Dict[str, str]], Dict[str, str]]
    """

    LOGGER.info("Appending to the video description...")
    LOGGER.info(locals())

    # Get the existing snippet details
    videos: yt_types.YouTubeVideoList = yt_livestream.YouTubeLivestream.execute_request(
        service.videos().list(id=video_id, part="id,snippet"))
    LOGGER.debug("Videos is: \n%s.", json.dumps(videos, indent=4))

    # Prepare a new title and description
    if isinstance(motion, dict):
        suffix = motion["suffix"]
        motion_desc = motion["description"]
    elif len(motion) == 0:
        suffix = "(no motion)"
        motion_desc = "No motion was detected in this video 😢."
    elif len(motion) == 1:
        suffix = "(1 action)"
        motion_desc = f"\n\nMotion was detected at {motion[0]['start']} for {motion[0]['duration']} second{'s' if motion[0]['duration'] != 1 else ''}.\n"
    else:
        suffix = f"({len(motion)} actions)"
        motion_desc = "\n\nMotion was detected at the following points:\n"
        for item in motion:
            motion_desc += f" • {item['start']} for {item['duration']} second{'s' if item['duration'] != 1 else ''}.\n"
    motion_desc += f"\n\n\nMOTION_DETECTION_PARAMS={MOTION_DETECTION_PARAMS}"

    # Prepare the body
    body = {"id": video_id, "snippet": {}}
    body["snippet"]["categoryId"] = videos["items"][0]["snippet"]["categoryId"]
    body["snippet"]["tags"] = videos["items"][0]["snippet"].get("tags", [])
    body["snippet"]["description"] = f"{videos['items'][0]['snippet']['description']} {motion_desc}"
    body["snippet"]["title"] = f"{videos['items'][0]['snippet']['title']} {suffix}"
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
        motion: List[Dict[str, str]]) -> None:
    """Send an email about the motion that was detected.

    :param config: the config to use
    :type config: configparser.SectionProxy
    :param video_id: the ID of the video
    :type video_id: str
    :param motion: a list of the motion events detected
    :type motion: List[Dict[str, str]]
    """

    LOGGER.info("Sending the motion email...")

    # Create the message
    message = MIMEMultipart("alternative")
    message["Subject"] = f"Motion detected in the birdbox ({len(motion)} event{'s' if len(motion) > 1 else ''})"
    message["To"] = config["to"]
    message["From"] = config["from"]
    message["Date"] = email.utils.formatdate()
    email_id = email.utils.make_msgid(domain=config["smtp_host"])
    message["Message-ID"] = email_id

    # Render the template
    with open("motion-email-template.html", encoding="ut-8") as file:
        template = Template(file.read())
        html = template.render(motion_timestamps=motion,
                               motion_params=MOTION_DETECTION_PARAMS,
                               video_url=f"https://youtu.be/{video_id}")

        # Create the plain-text version of the message
        text_maker = html2text.HTML2Text()
        text_maker.ignore_links = True
        text_maker.bypass_tables = False
        text = text_maker.handle(html)

    message.attach(MIMEText(text, "plain"))
    message.attach(MIMEText(html, "html"))

    LOGGER.debug("Message is: \n%s.", text)

    # Send the email
    utilities.send_email(config, message)

    LOGGER.info("Motion email sent successfully!\n")


def process_video(video_id: str, yt: google_services.YouTube,
                  yt_config: configparser.SectionProxy,
                  download_folder: Path, old_cwd: str,
                  email_config: configparser.SectionProxy):
    """Process a video.

    :param video_id: the YouTube ID of the video
    :type video_id: str
    :param yt: the YouTube object
    :type yt: google_services.YouTube
    :param yt_config: the config for YouTube
    :type yt_config: configparser.SectionProxy
    :param download_folder: the folder to download to
    :type download_folder: Path
    :param old_cwd: the starting working directory
    :type old_cwd: str
    :param email_config: the config for email
    :type email_config: configparser.SectionProxy
    """

    # pylint: disable=used-before-assignment
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
                                 {"suffix": "(no motion)",
                                  "description": "No motion was detected in this video as the recording is not available 😢."})
            print("Marked the video as having no motion.")

        return

    LOGGER.debug(
        "%s is %s big.",
        filename,
        humanize.naturalsize(
            os.path.getsize(filename)))

    if not args.download_only:

        # Run motion detection
        motion = get_motion_timestamps(filename)
        update_motion_status(
            yt.get_service(), video_id, motion)
        if len(motion) > 0:
            send_motion_email(email_config, video_id, motion)
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


def main():
    """Runs the motion detection script indefinitely."""

    # Get the config
    config = utilities.load_config(CONFIG_FILENAME)
    yt_config = config["YouTubeLivestream"]
    email_config = config["email"]
    motion_config = config["motion_detection"]

    # Save the directories
    old_cwd = os.getcwd()
    download_folder = Path(motion_config["download_folder"]) if \
        motion_config["download_folder"] != "" else Path(os.getcwd())

    try:

        # Get initial access to the YouTube API
        yt = yt_livestream.YouTubeLivestream(yt_config)
        yt.get_service()

        all_done = False
        while True:

            # Find out which videos need processing
            new_ids = []
            new_complete_broadcasts = yt.list_all_broadcasts(part="id,snippet,status", lifecycle_status=["complete"])
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
                process_video(video_id, yt, yt_config, download_folder, old_cwd, email_config)

            # Wait before repeating
            time.sleep(15 * 60)

    except Exception as error:
        LOGGER.exception("\n\nThere was an exception!!")
        os.chdir(old_cwd)
        LOGGER.debug("Changed working directory to %s.", os.getcwd())
        utilities.send_error_email(
            email_config, traceback.format_exc(), LOG_FILENAME)
        raise Exception from error  # pylint: disable=broad-exception-raised


if __name__ == "__main__":

    # Prepare the log
    LOGGER = utilities.prepare_logging(LOG_FILENAME)

    # Parse the args
    parser = argparse.ArgumentParser()
    parser.add_argument("-d", "--download-only", action="store_true")
    args = parser.parse_args()
    LOGGER.info("Args are: %s.", args)

    # Run it
    main()

else:
    LOGGER = logging.getLogger(__name__)
