import subprocess
import logging
import logging_config

root_logger = logging_config.setup_root_logging("clipboard.log")
logger = logging.getLogger(__name__)


def get_last_clipboard_text():
    """
    Returns the last clipboard item if it's text, otherwise returns None.
    Only works on macOS.
    """
    try:
        result = subprocess.run(["pbpaste"], capture_output=True, text=True, check=True)
        text = result.stdout
        # If clipboard is empty or not text, pbpaste returns empty string
        if text:
            logger.info("Clipboard text successfully retrieved")
            return text
        else:
            logger.warning("Clipboard is empty or not text")
            return None
    except Exception:
        logger.exception("Error getting clipboard text")
        return None


def set_clipboard_text(text):
    """
    Sets the clipboard contents to the given text.
    Only works on macOS.
    """
    try:
        process = subprocess.Popen(["pbcopy"], stdin=subprocess.PIPE)
        process.communicate(input=text.encode("utf-8"))
        logger.info("Prompt added to clipboard")
        return True
    except Exception:
        logger.exception("Error setting clipboard text")
        return False


if __name__ == "__main__":

    get_last_clipboard_text()
