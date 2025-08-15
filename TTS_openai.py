import asyncio
import openai
import pygame
import io
import tempfile
import threading
import time
from queue import Queue, Empty

import logging_config, logging
from openai.helpers import LocalAudioPlayer  # Add this import

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
DEFAULT_VOICE = "nova"
DEFAULT_MODEL = "gpt-4o-mini-tts"

logger = logging.getLogger(__name__)

from openai import AsyncOpenAI
from openai.helpers import LocalAudioPlayer  # Add this import


def speak_async_streaming(text: str) -> None:
    """
    Non-blocking TTS streaming playback for OpenAI TTS.
    Creates a new event loop in a background thread to avoid conflicts.
    """

    def _run_in_thread():
        """Run async TTS in a dedicated thread with its own event loop"""
        try:
            # Create a new event loop for this thread
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

            async def _async_play():
                logger.info(f"speak_async_streaming called with text: {text[:50]}...")
                try:
                    async with AsyncOpenAI().audio.speech.with_streaming_response.create(
                        model=DEFAULT_MODEL,
                        voice=DEFAULT_VOICE,
                        input=text,
                        response_format="pcm",
                        # Note: 'instructions' parameter may not be supported - remove if causing issues
                        # instructions="Speak in a cheerful and positive tone.",
                    ) as response:
                        logger.info(
                            "OpenAI streaming TTS response received, starting playback."
                        )
                        player = LocalAudioPlayer()
                        await player.play(response)
                        logger.info("Streaming audio playback finished.")
                except Exception as e:
                    logger.error(f"Exception in _async_play: {e}", exc_info=True)

            # Run the async function
            loop.run_until_complete(_async_play())

        except Exception as e:
            logger.error(f"Exception in _run_in_thread: {e}", exc_info=True)
        finally:
            # Clean up the event loop
            try:
                loop.close()
            except Exception as e:
                logger.error(f"Error closing event loop: {e}")

    # Start the thread
    thread = threading.Thread(target=_run_in_thread, daemon=True)
    thread.start()


# Keep your original speak_async for backward compatibility
async def speak_async(text, voice=DEFAULT_VOICE, model=DEFAULT_MODEL):
    """Start TTS but don't wait for completion (OpenAI TTS) - Legacy version"""
    logger.info(f"speak_async called with text={text!r}, voice={voice}, model={model}")
    try:
        logger.info("Requesting OpenAI TTS audio bytes (async)...")
        response = await asyncio.to_thread(
            lambda: openai.audio.speech.create(model=model, voice=voice, input=text)
        )
        audio_data = response.content
        logger.info("Received audio data from OpenAI TTS.")

        # Start playback in background thread - DON'T wait for it
        try:
            pygame.mixer.init()
            pygame.mixer.music.load(io.BytesIO(audio_data))
            pygame.mixer.music.play()
            while pygame.mixer.music.get_busy():
                time.sleep(0.1)
        except Exception as e:
            print(f"Error in background playback: {e}")

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
    while True:
        text = _play_queue.get()
        try:
            if not text:
                continue
            # Start async playback (returns immediately)
            asyncio.run(speak_async(text))
            # Wait for playback to start (up to ~2s)
            waited = 0.0
            while (
                not pygame.mixer.get_init() or not pygame.mixer.music.get_busy()
            ) and waited < 2.0:
                time.sleep(0.05)
                waited += 0.05
            # Then wait until it finishes
            while pygame.mixer.get_init() and pygame.mixer.music.get_busy():
                time.sleep(0.05)
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
    logger.info("Running TTS-openAI module as main. Testing play_speech().")
    asyncio.run(speak_async_streaming("Hello, this is a test!"))
