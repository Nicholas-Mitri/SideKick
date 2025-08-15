"""
Utilities for capturing screenshots on macOS using the native 'screencapture' CLI.
"""

import logging
import os
import platform
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Optional, Union
import logging_config

root_logger = logging_config.setup_root_logging("screen_grab.log")
logger = logging.getLogger(__name__)

__all__ = ("grab_area_interactive", "cleanup_tempfile")


def _ensure_macos_and_command() -> None:
    """
    Ensure the current environment supports interactive screenshot capture.
    Raises:
        NotImplementedError: If not running on macOS (Darwin).
        FileNotFoundError: If the 'screencapture' command is unavailable.
    """
    logger.debug("Checking if running on macOS and if 'screencapture' is available...")
    if platform.system() != "Darwin":
        logger.error("Not running on macOS (Darwin).")
        raise NotImplementedError(
            "grab_area_interactive is supported only on macOS (Darwin)."
        )
    if shutil.which("screencapture") is None:
        logger.error("'screencapture' command not found on this system.")
        raise FileNotFoundError(
            "The 'screencapture' command was not found on this system."
        )
    logger.debug("Environment check passed: macOS and 'screencapture' available.")


def grab_area_interactive(
    output_path: Optional[Union[str, Path]] = None,
    suppress_sound: bool = True,
) -> Optional[Path]:
    """
    Open macOS interactive selection (drag to select) for taking a screenshot.

    Args:
        output_path: The path where the screenshot will be saved.
            If None, a temporary file is created and used.
        suppress_sound: If True, disables the camera shutter sound during capture.

    Returns:
        Path: The path to the saved screenshot file if successful.
        None: If the user cancels the screenshot or the file is not created.

    Raises:
        NotImplementedError: If not running on macOS.
        FileNotFoundError: If the 'screencapture' command is unavailable.
        ValueError: If the parent directory of `output_path` does not exist.

    Notes:
        - Requires macOS Screen Recording permission for your terminal/IDE/Python.
    """
    logger.info("Starting interactive screenshot capture...")
    _ensure_macos_and_command()

    if output_path is None:
        fd, tmp_name = tempfile.mkstemp(suffix=".jpeg")
        os.close(fd)  # Prevent file descriptor leak
        target = Path(tmp_name)
        logger.debug("Created temporary file for screenshot: %s", target)
        # Remove placeholder so 'screencapture' creates the file anew.
        try:
            target.unlink(missing_ok=True)
            logger.debug("Removed placeholder temporary file: %s", target)
        except Exception as e:
            logger.warning("Could not remove placeholder temp file %s: %s", target, e)
            # Not critical; 'screencapture' can overwrite.
    else:
        target = Path(output_path)
        parent = target.parent
        if not parent.exists():
            logger.error("Parent directory does not exist: %s", parent)
            raise ValueError(f"Parent directory does not exist: {parent}")
        logger.debug("Using provided output path for screenshot: %s", target)

    # Build screencapture command for interactive selection
    cmd = [
        "screencapture",
        "-i",
    ]  # interactive; user can drag a rectangle or choose a window
    if suppress_sound:
        cmd.append("-x")  # no camera shutter sound

    logger.info("Running screencapture command: %s", " ".join(cmd + [str(target)]))
    # Run interactive capture
    result = subprocess.run(cmd + [str(target)], check=False)

    # If the user cancels the screenshot or the file was not created, clean up and return None
    if result.returncode != 0 or not target.exists():
        logger.info(
            "Screenshot cancelled or file not created (returncode=%s, exists=%s)",
            result.returncode,
            target.exists(),
        )
        if output_path is None and target.exists():
            try:
                target.unlink(missing_ok=True)
                logger.debug(
                    "Deleted temporary screenshot file after cancel: %s", target
                )
            except Exception as e:
                logger.warning(
                    "Failed to delete temporary screenshot %s: %s", target, e
                )
        return None

    logger.info("Screenshot saved to: %s", target)
    return target


def cleanup_tempfile(target: Union[str, Path]) -> bool:
    """
    Delete the file at the given path, useful for cleaning up temp screenshot files.

    Returns:
        bool: True if the file was deleted or did not exist; False if deletion failed.
    """
    try:
        Path(target).unlink(missing_ok=True)
        logger.debug("Deleted temporary file %s", target)
        return True
    except Exception as e:
        logger.warning("Error deleting temporary file %s: %s", target, e)
        return False


if __name__ == "__main__":
    logger.info("Running screen_grab.py as main. Invoking grab_area_interactive()...")
    cleanup_tempfile(grab_area_interactive())
