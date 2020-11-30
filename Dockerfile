FROM python:3.8-alpine
LABEL maintainer="Thomas Gorgolione <thomas@tgorg.com>"

RUN apk add --no-cache --update ffmpeg
COPY *.py /app/
COPY cache/ /app/cache/
COPY lib/ /app/lib/
COPY known_stations.json /app/
RUN touch /app/is_container

ENTRYPOINT ["python3", "/app/main.py"]
