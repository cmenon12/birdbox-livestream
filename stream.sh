#!/bin/sh

read -p "What's the RTMP URL? " url

while true
do
  raspivid -t 0 -w 1280 -h 720 -fps 25 -n -br 60 -co 10 -sh 70 -sa -100 -l -o - -a 1036 -a "%a %d %b %Y at %H:%M %Z" -ae 18,0xff,0x808000 -ISO 600 -b 2000000 | ffmpeg -re -ar 44100 -ac 2 -acodec pcm_s16le -f s16le -ac 2 -i /dev/zero -f h264 -i - -vcodec copy -acodec aac -ab 128k -g 50 -strict experimental -f flv -b:v 2000k -b:a 1k -maxrate 2000k -bufsize 1000k -preset veryfast $url
  sleep 30
done