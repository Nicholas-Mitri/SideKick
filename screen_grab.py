import subprocess
import tempfile
from pathlib import Path
from typing import Optional, Union

try:
    from PIL import Image
except ImportError:
    Image = None  # type: ignore


def grab_area_interactive(
    output_path: Optional[Union[str, Path]] = None, suppress_sound: bool = True
):
    """
    Opens macOS interactive selection (drag to select). Returns a PIL Image if Pillow is installed
    and no output_path is given; otherwise returns the saved Path. Returns None if user cancels.

    - Requires macOS Screen Recording permission for your terminal/IDE/Python.
    """
    if output_path is None:
        fd, tmp_name = tempfile.mkstemp(suffix=".jpeg")
        target = Path(tmp_name)
        target.unlink(missing_ok=True)  # Remove placeholder
    else:
        target = Path(output_path)

    # Build screencapture command
    cmd = [
        "screencapture",
        "-i",
    ]  # interactive; user can drag a rectangle or choose a window
    if suppress_sound:
        cmd.append("-x")  # no camera shutter sound

    # Run interactive capture
    result = subprocess.run(cmd + [str(target)], check=False)

    if result.returncode != 0 or not target.exists():
        if output_path is None and target.exists():
            target.unlink(missing_ok=True)
        return None
    # Always return target, regardless of output_path or PIL availability
    return target


def cleanup_tempfile(target: Union[str, Path]):
    """
    Deletes the file at the given path. Use for cleaning up temp screenshot files.
    """
    try:
        Path(target).unlink(missing_ok=True)
    except Exception as e:
        print(f"Error deleting temporary file {target}: {e}")


if __name__ == "__main__":
    grab_area_interactive()
