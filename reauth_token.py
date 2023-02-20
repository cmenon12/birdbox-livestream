"""Reauthorise and replace the Google API token."""
import configparser
import os

import youtube

__author__ = "Christopher Menon"
__credits__ = "Christopher Menon"
__license__ = "gpl-3.0"

# The token filenames to use
NEW_TOKEN_PICKLE_FILE = "token-new.pickle"
OLD_TOKEN_PICKLE_FILE = youtube.TOKEN_PICKLE_FILE

# The name of the config file
CONFIG_FILENAME = "config.ini"


def main():
    """Reauthorise and replace the token."""

    # Check that the config file exists
    try:
        open(CONFIG_FILENAME)
    except FileNotFoundError as error:
        print("The config file doesn't exist!")
        raise FileNotFoundError("The config file doesn't exist!") from error

    # Fetch info from the config
    parser = configparser.ConfigParser()
    parser.read(CONFIG_FILENAME)
    yt_config = parser["YouTubeLivestream"]

    # Reauthorise to a new file
    if os.path.exists(NEW_TOKEN_PICKLE_FILE):
        os.remove(NEW_TOKEN_PICKLE_FILE)
    yt = youtube.YouTube(yt_config)
    yt.get_service(auth_type=youtube.AuthorisationTypes.SSH, token_file=NEW_TOKEN_PICKLE_FILE)

    # Replace the old file
    if os.path.exists(OLD_TOKEN_PICKLE_FILE):
        os.remove(OLD_TOKEN_PICKLE_FILE)
    os.rename(NEW_TOKEN_PICKLE_FILE, OLD_TOKEN_PICKLE_FILE)


if __name__ == "__main__":
    main()
