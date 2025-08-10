import asyncio
import edge_tts
import pygame
import io
import tempfile
import threading
import time


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

    # Start playback but don't await it
    def play_in_background():
        pygame.mixer.init()
        pygame.mixer.music.load(io.BytesIO(audio_data))
        pygame.mixer.music.play()
        while pygame.mixer.music.get_busy():
            time.sleep(0.1)

    # Start thread and continue immediately
    threading.Thread(target=play_in_background, daemon=True).start()


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


if __name__ == "__main__":
    # Test speech generation
    asyncio.run(play_speech())
    # Test a voice
    asyncio.run(test_voice_realtime("en-US-AndrewNeural"))
