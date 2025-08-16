import sys, os
import re
import io
from typing import List, Optional
import threading
import queue
import time
import logging

from PyQt6.QtWidgets import (
    QApplication,
    QMainWindow,
    QVBoxLayout,
    QHBoxLayout,
    QWidget,
    QPushButton,
    QTextEdit,
    QLabel,
)
from PyQt6.QtCore import QThread, pyqtSignal, QObject

import openai
import pygame
from openai import OpenAI
import logging_config

logging_config.setup_root_logging("TTS_openai_streaming.log")
logger = logging.getLogger(__name__)

# Replace with your actual OpenAI API key
api_key = os.getenv("OPENAI_API_KEY")


class SentenceChunker:
    """Sophisticated sentence detection and chunking"""

    def __init__(self):
        # Pattern for sentence boundaries with sophisticated handling
        self.sentence_pattern = re.compile(
            r"(?<!\w\.\w.)(?<![A-Z][a-z]\.)(?<![A-Z]\.)(?<=\.|\!|\?)\s+(?=[A-Z])",
            re.MULTILINE,
        )

        # Common abbreviations that shouldn't end sentences
        self.abbreviations = {
            "Dr.",
            "Mr.",
            "Mrs.",
            "Ms.",
            "Prof.",
            "Sr.",
            "Jr.",
            "vs.",
            "etc.",
            "i.e.",
            "e.g.",
            "Inc.",
            "Ltd.",
            "Corp.",
            "U.S.",
            "U.K.",
            "a.m.",
            "p.m.",
        }

    def split_sentences(self, text: str):
        """Split text into sentences with sophisticated boundary detection.
        Returns (sentences, remainder) where remainder is the last incomplete chunk (if any).
        """
        text = text.strip()
        if not text:
            return [], ""

        # Handle special cases for abbreviations
        protected_text = text
        for abbr in self.abbreviations:
            protected_text = protected_text.replace(abbr, abbr.replace(".", "§"))

        # Split on sentence boundaries
        sentences = self.sentence_pattern.split(protected_text)

        # Restore periods and clean up
        result = []
        for sentence in sentences:
            sentence = sentence.replace("§", ".").strip()
            if sentence and len(sentence) > 1:
                result.append(sentence)

        # Determine if the last chunk is incomplete (no terminal punctuation)
        if result:
            last_original = sentences[-1].replace("§", ".").strip()
            if last_original and not re.search(r"[.!?]['\"\)\]]*\s*$", last_original):
                # Last chunk is incomplete
                remainder = result.pop()
            else:
                remainder = ""
        else:
            remainder = ""

        return result, remainder

    def create_chunks(self, text: str, chunk_size: int = 2):
        """Create chunks of specified sentence count"""
        sentences, remainder = self.split_sentences(text)
        chunks = []

        for i in range(0, len(sentences), chunk_size):
            chunk_sentences = sentences[i : i + chunk_size]
            chunk_text = " ".join(chunk_sentences)
            chunks.append(chunk_text)

        return chunks, remainder


class TTSService(QObject):
    """Persistent TTS service that stays active for the app lifetime"""

    error_occurred = pyqtSignal(str)
    chunk_generated = pyqtSignal(str)  # Signal when chunk audio is ready
    playback_started = pyqtSignal()
    playback_stopped = pyqtSignal()
    playback_finished = pyqtSignal()
    queue_status_changed = pyqtSignal(int)  # Number of items in queue

    def __init__(self, api_key: str):
        super().__init__()
        self.client = OpenAI(api_key=api_key)
        self.chunker = SentenceChunker()

        # Service state
        self.is_service_active = True
        self.is_playing = False
        self.should_stop_playback = False

        # Queues
        self.chunk_input_queue = queue.Queue()  # Text chunks to process
        self.audio_queue = queue.Queue()  # Generated audio data

        # Worker threads
        self.generation_thread = None
        self.playback_thread = None

        # Initialize pygame mixer
        pygame.mixer.init(frequency=22050, size=-16, channels=2, buffer=512)
        logger.info("Pygame mixer initialized.")

        # Tone setting for TTS Model
        self.TTS_instructions = None
        # Start the persistent worker threads
        self._start_service()

    def _start_service(self):
        """Start the persistent service threads"""
        if self.generation_thread is None or not self.generation_thread.is_alive():
            self.generation_thread = threading.Thread(
                target=self._generation_worker, daemon=True, name="TTSGenerationWorker"
            )
            self.generation_thread.start()
            logger.info("Generation worker thread started.")

        if self.playback_thread is None or not self.playback_thread.is_alive():
            self.playback_thread = threading.Thread(
                target=self._playback_worker, daemon=True, name="TTSPlaybackWorker"
            )
            self.playback_thread.start()
            logger.info("Playback worker thread started.")

    def _generation_worker(self):
        """Persistent thread that processes chunks sequentially"""
        logger.info("Generation worker started and waiting for chunks.")

        while self.is_service_active:
            try:
                # Get next chunk text (blocking with timeout)
                chunk_text = self.chunk_input_queue.get(timeout=1.0)

                if not self.is_service_active:
                    break

                logger.info(f"Generating audio for chunk: {chunk_text[:60]}...")

                # Generate audio for this chunk
                audio_data = self._generate_audio(chunk_text)
                if audio_data is not None:
                    self.audio_queue.put(audio_data)
                    self.chunk_generated.emit(chunk_text[:60] + "...")
                    logger.info("Audio chunk generated and queued.")

                # Update queue status
                self.queue_status_changed.emit(self.get_total_queue_size())

                # Mark task as done
                self.chunk_input_queue.task_done()

            except queue.Empty:
                # No chunks available, continue waiting
                continue
            except Exception as e:
                if self.is_service_active:
                    logger.error(f"Chunk generation error: {str(e)}")
                    self.error_occurred.emit(f"Chunk generation error: {str(e)}")

        logger.info("Generation worker exiting.")

    def _playback_worker(self):
        """Persistent thread for audio playback"""
        logger.info("Playback worker started and waiting for audio.")

        while self.is_service_active:
            try:
                if not self.is_playing:
                    time.sleep(0.1)  # Wait for play command
                    continue

                # Get next audio chunk (blocking with timeout)
                audio_data = self.audio_queue.get(timeout=1.0)

                if not self.is_service_active or self.should_stop_playback:
                    continue

                # Play the audio chunk
                logger.info("Playing audio chunk.")
                self._play_audio_chunk(audio_data)

                # Update queue status
                self.queue_status_changed.emit(self.get_total_queue_size())

            except queue.Empty:
                # No audio available, check if we should finish
                if (
                    self.is_playing
                    and self.audio_queue.empty()
                    and self.chunk_input_queue.empty()
                ):
                    logger.info("All queues empty, finishing playback.")
                    self._finish_playback()
                continue
            except Exception as e:
                if self.is_service_active:
                    logger.error(f"Playback error: {str(e)}")
                    self.error_occurred.emit(f"Playback error: {str(e)}")

        logger.info("Playback worker exiting.")

    def _generate_audio(self, text: str) -> Optional[bytes]:
        """Generate audio for a single chunk"""
        if not self.is_service_active:
            return None

        try:
            logger.info(f"Requesting TTS for: {text[:60]}...")
            response = self.client.audio.speech.create(
                model="gpt-4o-mini-tts",
                voice="coral",
                input=text,
                speed=1.0,
                response_format="mp3",
                instructions=self.TTS_instructions,  # You can customize this string as needed
            )
            logger.info("TTS audio received from OpenAI.")
            return response.content
        except Exception as e:
            logger.error(f"Audio generation failed: {str(e)}")
            self.error_occurred.emit(f"Audio generation failed: {str(e)}")
            return None

    def _play_audio_chunk(self, audio_data: bytes):
        """Play a single audio chunk"""
        if not self.is_service_active or self.should_stop_playback:
            return

        try:
            # Load audio data into pygame
            audio_file = io.BytesIO(audio_data)
            pygame.mixer.music.load(audio_file)
            pygame.mixer.music.play()
            logger.info("Audio chunk loaded and playback started.")

            # Wait for playback to complete (non-blocking check)
            while (
                pygame.mixer.music.get_busy()
                and not self.should_stop_playback
                and self.is_service_active
            ):
                time.sleep(0.05)  # Shorter sleep for more responsive stopping

            logger.info("Audio chunk playback finished.")

        except Exception as e:
            if self.is_service_active:
                logger.error(f"Exception during audio playback: {str(e)}")
                raise e

    def _finish_playback(self):
        """Called when playback naturally finishes"""
        self.is_playing = False
        self.should_stop_playback = False
        self.playback_finished.emit()
        logger.info("Playback naturally finished.")

    def add_chunk(self, chunk_text: str):
        """Add a single text chunk to the generation queue"""
        if not self.is_service_active:
            logger.warning("Cannot add chunk: service is not active.")
            return

        logger.info(f"Adding chunk to queue: {chunk_text[:60]}...")
        self.chunk_input_queue.put(chunk_text)
        self.queue_status_changed.emit(self.get_total_queue_size())
        logger.info(f"Queue size: {self.get_total_queue_size()}")

    def add_text(self, text: str):
        """Add full text (will be split into chunks)"""
        if not self.is_service_active:
            logger.warning("Cannot add text: service is not active.")
            return

        chunks, _ = self.chunker.create_chunks(text, 3)
        logger.info(f"Text split into {len(chunks)} chunks.")

        for chunk in chunks:
            self.add_chunk(chunk)

    def start_playback(self):
        """Start playing queued audio"""
        if not self.is_service_active:
            logger.warning("Cannot start playback: service is not active.")
            return

        if self.is_playing:
            logger.info("Playback is already running.")
            return

        logger.info("Starting playback.")
        self.is_playing = True
        self.should_stop_playback = False
        self.playback_started.emit()

    def stop_playback(self):
        """Stop playback and clear queues"""
        if not self.is_playing:
            logger.info("Playback is not currently running.")
            return

        logger.info("Stopping playback and clearing queues.")
        self.should_stop_playback = True
        self.is_playing = False

        # Stop current audio playback
        try:
            pygame.mixer.music.stop()
            logger.info("Audio playback stopped.")
        except Exception as e:
            logger.warning(f"Exception while stopping playback: {str(e)}")

        # Clear queues
        self._clear_queue(self.audio_queue)
        self._clear_queue(self.chunk_input_queue)

        self.queue_status_changed.emit(0)
        self.playback_stopped.emit()

    def _clear_queue(self, q):
        """Clear all items from a queue"""
        try:
            while not q.empty():
                q.get_nowait()
        except queue.Empty:
            pass

    def get_total_queue_size(self):
        """Get total number of items in all queues"""
        return self.chunk_input_queue.qsize() + self.audio_queue.qsize()

    def shutdown(self):
        """Shutdown the service"""
        logger.info("Shutting down TTS service.")
        self.is_service_active = False
        self.should_stop_playback = True
        self.is_playing = False

        # Stop current playback
        try:
            pygame.mixer.music.stop()
        except Exception:
            pass

        # Clear queues
        self._clear_queue(self.audio_queue)
        self._clear_queue(self.chunk_input_queue)

        # Wait for threads to finish
        if self.generation_thread and self.generation_thread.is_alive():
            self.generation_thread.join(timeout=2.0)
        if self.playback_thread and self.playback_thread.is_alive():
            self.playback_thread.join(timeout=2.0)

        logger.info("TTS service shutdown complete.")


class SimpleTTSApp(QMainWindow):
    """Simple TTS app with persistent service"""

    def __init__(self):
        super().__init__()
        self.tts_service = None
        self.tts_thread = None
        self.init_ui()
        self.init_tts_service()

    def init_ui(self):
        self.setWindowTitle("Persistent TTS Service - PyQt6")
        self.setGeometry(100, 100, 700, 500)

        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        layout = QVBoxLayout(central_widget)

        # Status label
        self.status_label = QLabel("Status: Ready")
        layout.addWidget(self.status_label)

        # Queue status label
        self.queue_label = QLabel("Queue: 0 items")
        layout.addWidget(self.queue_label)

        # Text input
        self.text_input = QTextEdit()
        self.text_input.setPlainText(
            "This is a sample text for testing the persistent TTS service. "
            "It contains multiple sentences to demonstrate the chunking functionality. "
            "Dr. Smith said that the system should handle abbreviations like U.S.A. correctly. "
            "Each chunk will be processed separately for better performance. "
            "The interface should remain responsive during playback. "
            "You can add multiple chunks before starting playback."
        )
        layout.addWidget(self.text_input)

        # Control buttons
        button_layout = QHBoxLayout()

        self.add_chunk_button = QPushButton("Add Chunk")
        self.add_chunk_button.clicked.connect(self.add_chunk)
        button_layout.addWidget(self.add_chunk_button)

        self.add_text_button = QPushButton("Add Full Text")
        self.add_text_button.clicked.connect(self.add_full_text)
        button_layout.addWidget(self.add_text_button)

        self.play_button = QPushButton("Play")
        self.play_button.clicked.connect(self.start_playback)
        button_layout.addWidget(self.play_button)

        self.stop_button = QPushButton("Stop & Clear")
        self.stop_button.clicked.connect(self.stop_playback)
        button_layout.addWidget(self.stop_button)

        layout.addLayout(button_layout)

        # Add some padding
        layout.addStretch()

    def init_tts_service(self):
        """Initialize the persistent TTS service"""
        # Create thread for TTS service
        self.tts_thread = QThread()
        self.tts_service = TTSService(api_key)
        self.tts_service.moveToThread(self.tts_thread)

        # Connect signals
        self.tts_service.error_occurred.connect(self.handle_error)
        self.tts_service.chunk_generated.connect(self.on_chunk_generated)
        self.tts_service.playback_started.connect(self.on_playback_started)
        self.tts_service.playback_stopped.connect(self.on_playback_stopped)
        self.tts_service.playback_finished.connect(self.on_playback_finished)
        self.tts_service.queue_status_changed.connect(self.on_queue_status_changed)

        # Start the thread
        self.tts_thread.start()
        logger.info("TTS service initialized and started.")

    def add_chunk(self):
        """Add current text as a single chunk"""
        text = self.text_input.toPlainText().strip()
        if not text:
            logger.info("No text to add as chunk.")
            return

        self.tts_service.add_chunk(text)
        logger.info("Chunk added to service.")

    def add_full_text(self):
        """Add current text (will be split into chunks)"""
        text = self.text_input.toPlainText().strip()
        if not text:
            logger.info("No text to add.")
            return

        self.tts_service.add_text(text)
        logger.info("Full text added to service.")

    def start_playback(self):
        """Start playing queued chunks"""
        self.tts_service.start_playback()

    def stop_playback(self):
        """Stop playback and clear queue"""
        self.tts_service.stop_playback()

    def handle_error(self, error_message: str):
        """Handle TTS errors"""
        logger.error(f"TTS Error: {error_message}")
        self.status_label.setText(f"Error: {error_message}")

    def on_chunk_generated(self, chunk_preview: str):
        """Called when a chunk is generated"""
        self.status_label.setText(f"Generated: {chunk_preview}")

    def on_playback_started(self):
        """Called when playback starts"""
        self.status_label.setText("Status: Playing")
        self.play_button.setEnabled(False)

    def on_playback_stopped(self):
        """Called when playback is stopped"""
        self.status_label.setText("Status: Stopped")
        self.play_button.setEnabled(True)

    def on_playback_finished(self):
        """Called when playback finishes naturally"""
        self.status_label.setText("Status: Finished")
        self.play_button.setEnabled(True)

    def on_queue_status_changed(self, queue_size: int):
        """Called when queue size changes"""
        self.queue_label.setText(f"Queue: {queue_size} items")

    def closeEvent(self, event):
        """Handle application close"""
        logger.info("Application closing.")
        if self.tts_service:
            self.tts_service.shutdown()

        if self.tts_thread and self.tts_thread.isRunning():
            self.tts_thread.quit()
            self.tts_thread.wait(3000)

        event.accept()


def main():
    app = QApplication(sys.argv)

    # Check for required packages
    try:
        import openai
        import pygame
    except ImportError as e:
        logger.error(f"Missing required package: {e}")
        print("Install with: pip install openai pygame")
        sys.exit(1)

    window = SimpleTTSApp()
    window.show()

    logger.info("Application started.")
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
