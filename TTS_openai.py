import asyncio
import openai
import pygame
import io
import tempfile
import threading
import time
from queue import Queue, Empty

import logging_config, logging

root_logger = logging_config.setup_root_logging("openai.log")
logger = logging.getLogger(__name__)

# Default OpenAI TTS voice and model
# Available OpenAI TTS voices = [
#     "alloy",
#     "ash",
#     "ballad",
#     "coral",
#     "echo",
#     "fable",
#     "onyx",
#     "nova",
#     "sage",
#     "shimmer",
#     "verse"
# ]
DEFAULT_VOICE = "ash"
DEFAULT_MODEL = "gpt-4o-mini-tts"


async def play_speech(
    text="Hello, this is a test!", voice=DEFAULT_VOICE, model=DEFAULT_MODEL
):
    """Play voice sample directly without saving to file using OpenAI TTS"""
    logger.info(f"play_speech called with text={text!r}, voice={voice}, model={model}")
    try:
        logger.info("Requesting OpenAI TTS audio bytes...")
        response = await asyncio.to_thread(
            lambda: openai.audio.speech.create(model=model, voice=voice, input=text)
        )
        audio_data = response.content
        logger.info("Received audio data from OpenAI TTS.")

        logger.info("Initializing pygame mixer for playback.")
        pygame.mixer.init()
        pygame.mixer.music.load(io.BytesIO(audio_data))
        pygame.mixer.music.play()
        logger.info("Audio playback started.")

        # Wait for playback to finish
        while pygame.mixer.music.get_busy():
            await asyncio.sleep(0.1)
        logger.info("Audio playback finished.")
    except Exception as e:
        logger.error(f"Error in play_speech: {e}", exc_info=True)


async def speak_async(text, voice=DEFAULT_VOICE, model=DEFAULT_MODEL):
    """Start TTS but don't wait for completion (OpenAI TTS)"""
    logger.info(f"speak_async called with text={text!r}, voice={voice}, model={model}")
    try:
        logger.info("Requesting OpenAI TTS audio bytes (async)...")
        response = await asyncio.to_thread(
            lambda: openai.audio.speech.create(model=model, voice=voice, input=text)
        )
        audio_data = response.content
        logger.info("Received audio data from OpenAI TTS.")

        def play_in_background():
            try:
                logger.info("Initializing pygame mixer for background playback.")
                pygame.mixer.init()
                pygame.mixer.music.load(io.BytesIO(audio_data))
                pygame.mixer.music.play()
                logger.info("Background audio playback started.")
                while pygame.mixer.music.get_busy():
                    time.sleep(0.1)
                logger.info("Background audio playback finished.")
            except Exception as e:
                logger.error(f"Error in play_in_background: {e}", exc_info=True)

        # Start thread and continue immediately
        threading.Thread(target=play_in_background, daemon=True).start()
    except Exception as e:
        logger.error(f"Error in speak_async: {e}", exc_info=True)


async def save_speech(
    text="Hello, this is a test!", voice=DEFAULT_VOICE, model=DEFAULT_MODEL
):
    """
    Generates speech from text using OpenAI TTS, saves to a temp file, and returns the file path.
    The caller is responsible for cleaning up the temp file using clean_tmp.
    """
    logger.info(f"save_speech called with text={text!r}, voice={voice}, model={model}")
    try:
        logger.info("Requesting OpenAI TTS audio bytes for saving...")
        response = await asyncio.to_thread(
            lambda: openai.audio.speech.create(model=model, voice=voice, input=text)
        )
        audio_data = response.content
        logger.info("Received audio data from OpenAI TTS.")

        tmpfile = tempfile.NamedTemporaryFile(suffix=".mp3", delete=False)
        tmpfile.write(audio_data)
        tmpfile.close()
        logger.info(f"Speech saved to temporary file: {tmpfile.name}")
        print(f"Speech saved to temporary file: {tmpfile.name}")
        return tmpfile.name
    except Exception as e:
        logger.error(f"Error in save_speech: {e}", exc_info=True)
        raise


def clean_tmp_audio(tmpfile_path):
    """
    Deletes the temporary file at the given path.
    """
    import os

    logger.info(f"Attempting to delete temporary file: {tmpfile_path}")
    try:
        os.remove(tmpfile_path)
        logger.info(f"Temporary file {tmpfile_path} deleted.")
        print(f"Temporary file {tmpfile_path} deleted.")
    except Exception as e:
        logger.error(
            f"Error deleting temporary file {tmpfile_path}: {e}", exc_info=True
        )
        print(f"Error deleting temporary file {tmpfile_path}: {e}")


_play_queue = Queue()
_worker_started = False


def _tts_worker():
    logger.info("TTS worker thread started.")
    while True:
        text = _play_queue.get()
        try:
            if not text:
                logger.info("TTS worker received empty text, skipping.")
                continue
            logger.info(f"TTS worker received text to speak: {text!r}")
            # Start async playback (returns immediately)
            asyncio.run(speak_async(text))
            # Wait for playback to start (up to ~2s)
            waited = 0.0
            while (
                not pygame.mixer.get_init() or not pygame.mixer.music.get_busy()
            ) and waited < 2.0:
                time.sleep(0.05)
                waited += 0.05
            logger.info("TTS worker playback started, waiting for finish.")
            # Then wait until it finishes
            while pygame.mixer.get_init() and pygame.mixer.music.get_busy():
                time.sleep(0.05)
            logger.info("TTS worker playback finished.")
        except Exception as e:
            logger.error(f"Error in TTS worker: {e}", exc_info=True)
        finally:
            _play_queue.task_done()


def _ensure_worker():
    global _worker_started
    if not _worker_started:
        logger.info("Starting TTS worker thread.")
        threading.Thread(target=_tts_worker, daemon=True).start()
        _worker_started = True
    else:
        logger.info("TTS worker thread already started.")


def enqueue(text: str):
    logger.info(f"Enqueue called with text: {text!r}")
    _ensure_worker()
    _play_queue.put(text)
    logger.info("Text enqueued for TTS playback.")


def clear():
    logger.info("Clearing TTS playback and queue.")
    # stop any current audio and empty the queue
    try:
        pygame.mixer.music.stop()
        logger.info("Stopped current audio playback.")
    except Exception as e:
        logger.warning(f"Exception while stopping audio: {e}")
    try:
        while True:
            _play_queue.get_nowait()
            _play_queue.task_done()
        logger.info("Cleared all items from TTS queue.")
    except Empty:
        logger.info("TTS queue was already empty.")


if __name__ == "__main__":
    # Test speech generation
    logger.info("Running TTS-openAI module as main. Testing play_speech().")
    asyncio.run(play_speech())
