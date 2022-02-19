"""Reauthorise and replace the Google API token."""

import os

import main as yt_livestream

NEW_TOKEN_PICKLE_FILE = "new-token.pickle"
OLD_TOKEN_PICKLE_FILE = yt_livestream.TOKEN_PICKLE_FILE


def main():
    """Reauthorise and replace the token."""

    # Reauthorise to a new file
    if os.path.exists(NEW_TOKEN_PICKLE_FILE):
        os.remove(NEW_TOKEN_PICKLE_FILE)
    service = yt_livestream.YouTubeLivestream.get_service(
        token_file=NEW_TOKEN_PICKLE_FILE)

    # Replace the old file
    if os.path.exists(OLD_TOKEN_PICKLE_FILE):
        os.remove(OLD_TOKEN_PICKLE_FILE)
    os.rename(NEW_TOKEN_PICKLE_FILE, OLD_TOKEN_PICKLE_FILE)


if __name__ == "__main__":
    main()
