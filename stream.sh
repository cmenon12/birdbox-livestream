#!/bin/bash

read -e -p "What's the RTMP URL? " url

while true
do
  raspivid -t 0 -w 1280 -h 720 -fps 25 -n -br 60 -co 10 -sh 70 -sa -100 -l -o - -a 1036 -a "%a %d %b %Y at %H:%M:%S %Z" -ae 18,0xff,0x808000 -ISO 600 -b 4200000 | ffmpeg -re -stream_loop -1 -i ./music/all-variable-120-mono.mp3 -i - -map 1:v -map 0:a -vcodec copy -acodec copy -ab 128k -g 50 -strict experimental -f flv -b:v 4200k -b:a 40k -maxrate 4240k -preset veryfast $url -report

  #   raspivid -t 0 -w 1280 -h 720 -fps 25 -n -br 60 -co 10 -sh 70 -sa -100 -l -o - -a 1036 -a "%a %d %b %Y at %H:%M %Z" -ae 18,0xff,0x808000 -ISO 600 -b 2800000 | ffmpeg -re -ar 44100 -ac 2 -acodec pcm_s16le -f s16le -ac 2 -i /dev/zero -f h264 -i - -vcodec copy -acodec aac -ab 128k -g 50 -strict experimental -f flv -b:v 2800k -b:a 1k -maxrate 2800k -bufsize 1400k -preset veryfast $url

  sleep 30
done
