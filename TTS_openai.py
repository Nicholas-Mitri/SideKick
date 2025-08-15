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
import asyncio

from openai import AsyncOpenAI
from openai.helpers import LocalAudioPlayer

openai = AsyncOpenAI()


async def speak_async_streaming(text: str) -> None:
    logger.info(f"speak_async_streaming called with text={text!r}")
    try:
        async with openai.audio.speech.with_streaming_response.create(
            model="gpt-4o-mini-tts",
            voice=DEFAULT_VOICE,
            input=text,
            instructions="Speak in a cheerful and positive tone.",
            response_format="pcm",
        ) as response:
            logger.info("OpenAI streaming TTS response received, starting playback.")
            await LocalAudioPlayer().play(response)
            logger.info("Streaming audio playback finished.")
    except Exception as e:
        logger.error(f"Exception in speak_async_streaming: {e}", exc_info=True)


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
    except Exception as e:
        logger.error(f"Error in speak_async: {e}", exc_info=True)


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


if __name__ == "__main__":
    # Test speech generation
    logger.info("Running TTS-openAI module as main. Testing play_speech().")
    asyncio.run(speak_async_streaming("Hello, this is a test!"))
