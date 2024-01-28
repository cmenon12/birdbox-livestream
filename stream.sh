#!/bin/bash

read -e -p "What's the RTMP URL? " url

while true
do
  # -t timeout in ms before stopping capture, 0 to disable
  # -w width
  # -h height
  # -fps frames per second
  # -n no preview window
  # -br brightness, 0 to 100
  # -co contrast, -100 to 100
  # -sh sharpness, -100 to 100
  # -sa saturation, -100 to 100
  # -l listen on a TCP socket
  # -o output to stdout
  # -a set annotate flags or text
  # -a annotate string
  # -ae set annotate text size, text colour, and background colour
  # -ISO set capture ISO
  # -b set bitrate in bits per second
  raspivid -t 0 -w 1280 -h 720 -fps 25 -n -br 60 -co 10 -sh 70 -sa -100 -l -o - -a 1036 -a "%a %d %b %Y at %H:%M:%S %Z" -ae 18,0xff,0x808000 -ISO 600 -b 3500000 |

  # -re read input at the native framerate
  # -stream_loop loop input indefinitely
  # -i input file
  # -i input from stdin
  # -map use the video from the second input
  # -map use the audio from the first input
  # -vcodec use the same video codec as the input
  # -acodec use the same audio codec as the input
  # -strict how strictly to conform to the codecs
  # -f set format
  # -b set the video bitrate
  # -b set the audio bitrate
  # -maxrate set the maximum bitrate
  # -preset compression to encoding speed ration, faster=CPU keeps up better
  # the url variable
  # -report dump to a log file
  ffmpeg -re -stream_loop -1 -i ./music/all-variable-120-mono.mp3 -i - -map 1:v -map 0:a -vcodec copy -acodec copy -strict normal -f flv -b:v 3500k -b:a 40k -maxrate 3540k -preset ultrafast $url -report

  sleep 30
done
