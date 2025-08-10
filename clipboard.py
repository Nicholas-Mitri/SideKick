import subprocess


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
            return text
        else:
            return None
    except Exception:
        return None


def set_clipboard_text(text):
    """
    Sets the clipboard contents to the given text.
    Only works on macOS.
    """
    try:
        process = subprocess.Popen(["pbcopy"], stdin=subprocess.PIPE)
        process.communicate(input=text.encode("utf-8"))
        return True
    except Exception:
        return False
