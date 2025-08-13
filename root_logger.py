import sys, os
import logging


def setup_root_logging(
    output_log_filename="output-log.log",
    console_level=logging.INFO,
    file_level=logging.DEBUG,
    file_mode="w",
):
    """
    Set up root logging configuration for the application.

    This function configures the root logger to log messages to both a file and the console.
    The log file will be created in the 'logs' directory (created if it does not exist).
    The file handler logs all messages at or above `file_level`, while the console handler
    logs messages at or above `console_level`. The log format includes timestamp, level, logger name, and message.

    Args:
        output_log_filename (str): Name of the log file to write logs to (default: "output-log.log").
        console_level (int): Logging level for the console handler (default: logging.INFO).
        file_level (int): Logging level for the file handler (default: logging.DEBUG).
        file_mode (str): File mode for the log file, e.g., "w" for overwrite or "a" for append (default: "w").
    """
    log_directory = "logs"
    if not os.path.exists(log_directory):
        os.makedirs(log_directory)

    # Set up logging to both file and console, with different levels per handler
    file_handler = logging.FileHandler(f"logs/{output_log_filename}", mode=file_mode)
    file_handler.setLevel(file_level)  # Log everything to file

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(console_level)  # Only log INFO and above to console

    formatter = logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
    file_handler.setFormatter(formatter)
    console_handler.setFormatter(formatter)

    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG)
    # Avoid adding handlers multiple times if this module is reloaded
    if not root_logger.handlers:
        root_logger.addHandler(file_handler)
        root_logger.addHandler(console_handler)
    else:
        # Remove all handlers and re-add to avoid duplicate logs
        root_logger.handlers.clear()
        root_logger.addHandler(file_handler)
        root_logger.addHandler(console_handler)
