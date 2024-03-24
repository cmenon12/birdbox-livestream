<img align="left" width="65" height="65" alt="Logo cartoon of birdbox with CCTV inside" src="/assets/logo.png">

# birdbox-livestream

This is a small collection of Python scripts designed for livestreaming a birdbox from a Raspberry Pi to YouTube!

This is to test the in-solidarity bot and won't be merged! He is the developer. The main system is broken.

### **[Check out the channel on YouTube!](https://www.youtube.com/channel/UCikUXkTwFvyrHlajBRQwvuw)**

**(unfortunately no birds have shown up yet 😢)**

[<img src="/assets/my-birdbox.png" alt="Photo of wooden birdbox on a red brick wall with a CCTV warning on the side" width="500" />](https://www.youtube.com/channel/UCikUXkTwFvyrHlajBRQwvuw)

[![GitHub license](https://img.shields.io/github/license/cmenon12/birdbox-livestream?style=flat)](https://github.com/cmenon12/birdbox-livestream/blob/master/LICENSE)

## The Python Scripts

#### [`yt_livestream.py`](yt_livestream.py)

This script has the livestreaming capability. When run directly, it connects to the YouTube API and creates a livestream
with a RTMP URL. Once it detects that you've started sending data to the livestream, it schedules broadcasts for every
six hours. These have complete titles, descriptions, tags, etc., and are arranged into weekly playlists. Each broadcast
is started & stopped on schedule.

The `YouTube` class manages the connection to the API. The `YouTubeLivestream` class inherits `YouTube`, and provides
the full livestreaming functionality. This separation allows other scripts to use the YouTube API without directly
managing any livestreams.

This runs indefinitely, and will send an email if any errors occur. Fluctuations in your internet connection (e.g. those
that might cause some sort of `IOError`) are handled with a delay & retry.

#### [`motion_detection.py`](motion_detection.py)

This script performs motion detection on the completed broadcasts. Once a broadcast completes (new broadcasts are polled
for regularly) it's downloaded in 144p, motion detection is run on it, and the result is appended to the video's title &
description. If any motion is detected, the timestamps are added to the description and emailed to the user.

This script relies on `yt_livestream.py` for connecting to the YouTube API and sending error emails.

#### [`yt_cleanup.py`](yt_cleanup.py)

This script is used to clean up old videos and weekly playlists, either by deleting them or making them private. It can
clean up a subset of them between two specified dates. Be careful not to exceed
the [daily YouTube API quota](https://developers.google.com/youtube/v3/getting-started#quota) using this tool.

#### [`reauth_token.py`](reauth_token.py)

This is just used to force a reauthorisation with the YouTube API and generate a brand-new refresh token.

## Other Scripts

#### [`stream.sh`](stream.sh)

This little bash script runs the livestreaming. It asks for the RTMP URL, and then starts capturing video
with `raspivid`, piping that into `ffmpeg` where it's combined with an audio file and output to the RTMP URL. If the
command exits for any reason (e.g. some sort of IO error because the internet drops) it restarts after 30 seconds.

## License & Attributions

[GNU GPLv3](https://choosealicense.com/licenses/gpl-3.0/)

[Nest icon created by iconixar - Flaticon.](https://www.flaticon.com/free-icons/nest) [CCTV icon created by Freepik - Flaticon.](https://www.flaticon.com/free-icons/cctv)
