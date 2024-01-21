"""Reauthorise and replace the Google API token."""
import configparser
import os

import google_services
import utilities

__author__ = "Christopher Menon"
__credits__ = "Christopher Menon"
__license__ = "gpl-3.0"

# The token filenames to use
NEW_TOKEN_PICKLE_FILE = "youtube_v3_new.pickle"
OLD_TOKEN_PICKLE_FILE = "youtube_v3.pickle"

# The name of the config file
CONFIG_FILENAME = "config.ini"


def main():
    """Reauthorise and replace the token."""

    # Get the config
    parser = utilities.load_config(CONFIG_FILENAME)
    yt_config: configparser.SectionProxy = parser["YouTubeLivestream"]

    # Reauthorise to a new file
    if os.path.exists(NEW_TOKEN_PICKLE_FILE):
        os.remove(NEW_TOKEN_PICKLE_FILE)
    yt = google_services.YouTube(yt_config, token_file=NEW_TOKEN_PICKLE_FILE)
    yt.get_service(auth_type=google_services.AuthorisationTypes.SSH)

    # Replace the old file
    if os.path.exists(OLD_TOKEN_PICKLE_FILE):
        os.remove(OLD_TOKEN_PICKLE_FILE)
    os.rename(NEW_TOKEN_PICKLE_FILE, OLD_TOKEN_PICKLE_FILE)


if __name__ == "__main__":
    main()
