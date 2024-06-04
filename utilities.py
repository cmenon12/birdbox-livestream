import configparser
import email.utils
import logging
import re
import smtplib
import ssl
import sys
import time
from email import encoders
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path


class DatetimeFormat:
    """A class to hold the datetime format strings."""

    @staticmethod
    def time_fmt(sep: str = ":", seconds: bool = True, tz: bool = False) -> str:
        """Returns the time format string.

        :param sep: the separator to use
        :type sep: str
        :param seconds: whether to include seconds
        :type seconds: bool
        :param tz: whether to include the timezone
        :type tz: bool
        :return: the time format string
        :rtype: str
        """

        return f"%H{sep}%M{f'{sep}%S' if seconds else ''}{' %Z' if tz else ''}"

    @staticmethod
    def date_fmt(sep: str = "-") -> str:
        """Returns the date format string.

        :param sep: the separator to use
        :type sep: str
        :return: the date format string
        :rtype: str
        """

        return f"%Y{sep}%m{sep}%d"

    @staticmethod
    def datetime_fmt(sep: str = " ", date_sep: str = "-", time_sep: str = ":",
                     seconds: bool = True, tz: bool = False) -> str:
        """Returns the datetime format string.

        :param sep: the separator to use
        :type sep: str
        :param date_sep: the date separator to use
        :type date_sep: str
        :param time_sep: the time separator to use
        :type time_sep: str
        :param seconds: whether to include seconds
        :type seconds: bool
        :param tz: whether to include the timezone
        :type tz: bool
        :return: the datetime format string
        :rtype: str
        """

        return f"{DatetimeFormat.date_fmt(date_sep)}{sep}{DatetimeFormat.time_fmt(time_sep, seconds, tz)}"

    @staticmethod
    def pretty_date_fmt(day: bool = True, year: bool = True) -> str:
        """Returns the pretty date format string.

        :param day: whether to include the day
        :type day: bool
        :param year: whether to include the year
        :type year: bool
        :return: the pretty date format string
        :rtype: str
        """

        return f"{'%a ' if day else ''}%d %b{' %Y' if year else ''}"

    @staticmethod
    def pretty_datetime_fmt(day: bool = True, year: bool = True, time_sep: str = ":",
                            seconds: bool = True, tz: bool = False) -> str:
        """Returns the pretty datetime format string.

        :param day: whether to include the day
        :type day: bool
        :param year: whether to include the year
        :type year: bool
        :param time_sep: the time separator to use
        :type time_sep: str
        :param seconds: whether to include seconds
        :type seconds: bool
        :param tz: whether to include the timezone
        :type tz: bool
        :return: the pretty datetime format string
        :rtype: str
        """

        return f"{DatetimeFormat.pretty_date_fmt(day, year)} at {DatetimeFormat.time_fmt(time_sep, seconds, tz)}"


def prepare_logging(filename: str) -> logging.Logger:
    """Prepares logging for the application.

    :param filename: the name of the file that's being logged
    :type filename: str
    :return: the logger
    :rtype: logging.Logger
    """

    Path("./logs").mkdir(parents=True, exist_ok=True)
    formatter = logging.Formatter(
        "%(asctime)s | %(levelname)5s in %(module)s.%(funcName)s() on line %(lineno)-3d | %(message)s"
    )
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    console_handler.setLevel(logging.INFO)

    file_handler = logging.FileHandler(
        f"./logs/{filename}",
        encoding="utf-8"
    )
    file_handler.setFormatter(formatter)
    file_handler.setLevel(logging.DEBUG)

    logger = logging.getLogger()
    logger.setLevel(logging.DEBUG)
    logger.addHandler(console_handler)
    logger.addHandler(file_handler)
    return logger


def load_config(filename: str) -> configparser.ConfigParser():
    """Loads the config file.

    :param filename: the name of the config file
    :type filename: str
    :return: the config parser
    :rtype: configparser.ConfigParser
    """

    # Check that the config file exists
    try:
        open(filename)  # pylint: disable=unspecified-encoding
        LOGGER.info("Loaded config %s.", filename)
    except FileNotFoundError as error:
        LOGGER.error("Could not find config %s, exiting.", filename)
        time.sleep(5)
        raise FileNotFoundError("The config file doesn't exist!") from error

    # Fetch info from the config
    parser = configparser.ConfigParser()
    parser.read(filename)

    return parser


def send_email(config: configparser.SectionProxy, message: MIMEMultipart):
    """Send an email.

    :param config: the config for the email
    :type config: configparser.SectionProxy
    :param message: the message to send
    :type message: MIMEMultipart
    """

    with smtplib.SMTP_SSL(config["smtp_host"],
                          int(config["smtp_port"]),
                          context=ssl.create_default_context()) as server:
        server.login(config["username"], config["password"])
        server.sendmail(re.findall("(?<=<)\\S+(?=>)", config["from"])[0],
                        re.findall("(?<=<)\\S+(?=>)", config["to"]),
                        message.as_string())


def send_error_email(config: configparser.SectionProxy, trace: str,
                     filename: str) -> None:
    """Send an email about the error.

    :param config: the config for the email
    :type config: configparser.SectionProxy
    :param trace: the stack trace of the exception
    :type trace: str
    :param filename: the filename of the log file to attach
    :type filename: str
    """

    LOGGER.info("Sending the error email...")

    # Create the message
    message = MIMEMultipart("alternative")
    message["Subject"] = "ERROR with birdbox-livestream!"
    message["To"] = config["to"]
    message["From"] = config["from"]
    message["X-Priority"] = "1"
    message["Date"] = email.utils.formatdate()
    email_id = email.utils.make_msgid(domain=config["smtp_host"])
    message["Message-ID"] = email_id

    # Create and attach the text
    text = f"{trace}\n\n———\nThis email was sent automatically by a computer program (" \
           f"https://github.com/cmenon12/birdbox-livestream). "
    message.attach(MIMEText(text, "plain"))

    LOGGER.debug("Message is: \n%s.", message)

    # Attach the log
    part = MIMEBase("text", "plain")
    part.set_payload(open(f"./logs/{filename}", "r").read())  # pylint: disable=unspecified-encoding
    encoders.encode_base64(part)
    part.add_header("Content-Disposition",
                    f"attachment; filename=\"{filename}\"")
    part.add_header("Content-Description",
                    f"{filename}")
    message.attach(part)

    # Send the email
    send_email(config, message)

    LOGGER.info("Error email sent successfully!\n")


LOGGER = logging.getLogger(__name__)
