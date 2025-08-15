import asyncio
import edge_tts
import pygame
import io
import tempfile
import threading
import time
from queue import Queue, Empty
import logging, logging_config

logging_config.setup_root_logging("edge_tts.log")
logger = logging.getLogger(__name__)


async def play_speech(text="Hello, this is a test!", voice="en-US-AndrewNeural"):
    """Play voice sample directly without saving to file"""

    communicate = edge_tts.Communicate(text, voice)

    # Get audio data as bytes
    audio_data = b""
    async for chunk in communicate.stream():
        if chunk["type"] == "audio":
            audio_data += chunk["data"]

    # Play using pygame (you'll need: pip install pygame)
    pygame.mixer.init()
    pygame.mixer.music.load(io.BytesIO(audio_data))
    pygame.mixer.music.play()

    # Wait for playback to finish
    while pygame.mixer.music.get_busy():
        await asyncio.sleep(0.1)


async def speak_async(text, voice="en-US-AndrewNeural"):
    """Start TTS but don't wait for completion"""
    communicate = edge_tts.Communicate(text, voice)
    audio_data = b""
    async for chunk in communicate.stream():
        if chunk["type"] == "audio":
            audio_data += chunk["data"]

    pygame.mixer.init()
    pygame.mixer.music.load(io.BytesIO(audio_data))
    pygame.mixer.music.play()
    while pygame.mixer.music.get_busy():
        time.sleep(0.1)


async def save_speech(text="Hello, this is a test!", voice="en-US-AndrewNeural"):
    """
    Generates speech from text using edge_tts, saves to a temp file, and returns the file path.
    The caller is responsible for cleaning up the temp file using clean_tmp.
    """
    communicate = edge_tts.Communicate(text, voice)
    tmpfile = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
    tmpfile.close()  # Close so edge_tts can write to it
    await communicate.save(tmpfile.name)
    print(f"Speech saved to temporary file: {tmpfile.name}")
    return tmpfile.name


def clean_tmp_audio(tmpfile_path):
    """
    Deletes the temporary file at the given path.
    """
    import os

    try:
        os.remove(tmpfile_path)
        print(f"Temporary file {tmpfile_path} deleted.")
    except Exception as e:
        print(f"Error deleting temporary file {tmpfile_path}: {e}")


_play_queue = Queue()
_worker_started = False


def _tts_worker():

    while True:
        text = _play_queue.get()
        try:
            if not text:
                logger.debug("Received empty text from queue, skipping.")
                continue
            logger.info(f"Starting TTS playback for text: {text[:50]}...")
            # Start async playback (returns immediately)
            try:
                asyncio.run(speak_async(text))
            except Exception as e:
                logger.error("Exception in _tts_worker:", exc_info=True)
                logger.error(f"Exception in _tts_worker: {e}")

            # Wait for playback to start (up to ~2s)
            waited = 0.0
            try:
                while (
                    not pygame.mixer.get_init() or not pygame.mixer.music.get_busy()
                ) and waited < 2.0:
                    time.sleep(0.05)
                    waited += 0.05

                if waited >= 2.0:
                    logger.warning("Playback did not start within 2 seconds.")
            except Exception as e:
                logger.error("Exception in _tts_worker:", exc_info=True)
                logger.error(f"Exception in _tts_worker: {e}")
            # Then wait until it finishes
            while pygame.mixer.get_init() and pygame.mixer.music.get_busy():
                time.sleep(0.05)
            logger.info("TTS playback finished.")
        except Exception as e:
            logger.error(f"Exception in _tts_worker: {e}", exc_info=True)
        finally:
            _play_queue.task_done()


def _ensure_worker():
    global _worker_started
    if not _worker_started:
        threading.Thread(target=_tts_worker, daemon=True).start()
        _worker_started = True


def enqueue(text: str):
    _ensure_worker()
    _play_queue.put(text)


def clear():
    # stop any current audio and empty the queue
    try:
        pygame.mixer.music.stop()
    except Exception:
        pass
    try:
        while True:
            _play_queue.get_nowait()
            _play_queue.task_done()
    except Empty:
        pass


if __name__ == "__main__":
    # Test speech generation
    asyncio.run(speak_async("Hello, this is a test!"))
