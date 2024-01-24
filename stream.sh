#!/bin/bash

read -e -p "What's the RTMP URL? " url

while true
do
  raspivid \
    -t 0 \        # timeout in ms before stopping capture, 0 to disable
    -w 1280 \     # width
    -h 720 \      # height
    -fps 25 \     # frames per second
    -n \          # don't display a preview window
    -br 60 \      # brightness, 0 to 100
    -co 10 \      # contrast, -100 to 100
    -sh 70 \      # sharpness, -100 to 100
    -sa -100 \    # saturation, -100 to 100
    -l \          # listen on a TCP socket
    -o - \        # output to stdout
    -a 1036 \     # set annotate flags or text
    -a "%a %d %b %Y at %H:%M:%S %Z" \   # annotate string
    -ae 18,0xff,0x808000 \              # set annotation text size, text colour, and background colour
    -ISO 600 \          # set capture ISO
    -b 4000000 |        # set bitrate in bits per second
  ffmpeg -re \        # read input at the native framerate
    -stream_loop -1 \   # loop indefinitely
    -i ./music/all-variable-120-mono.mp3 \  # input file
    -i - \              # input from stdin
    -map 0:a \          # use the video from the second input
    -map 1:v \          # use the audio from the first input
    -vcodec copy \      # use the same video codec as the input
    -acodec copy \      # use the same audio codec as the input
    -ab 128k \
    -g 50
    -strict experimental  # should change to normal
    -f flv              # set format
    -b:v 4000k          # set the video bitrate
    -b:a 40k            # set the audio bitrate
    -maxrate 4040k      # set the maximum bitrate
    -preset veryfast
    $url
    -report             # dump to a log file

  #   raspivid -t 0 -w 1280 -h 720 -fps 25 -n -br 60 -co 10 -sh 70 -sa -100 -l -o - -a 1036 -a "%a %d %b %Y at %H:%M %Z" -ae 18,0xff,0x808000 -ISO 600 -b 2800000 | ffmpeg -re -ar 44100 -ac 2 -acodec pcm_s16le -f s16le -ac 2 -i /dev/zero -f h264 -i - -vcodec copy -acodec aac -ab 128k -g 50 -strict experimental -f flv -b:v 2800k -b:a 1k -maxrate 2800k -bufsize 1400k -preset veryfast $url

  sleep 30
done
