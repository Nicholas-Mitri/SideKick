import sys, os
import re
import io
from typing import List, Optional
import threading
import queue
import time

from PyQt6.QtWidgets import (
    QApplication,
    QMainWindow,
    QVBoxLayout,
    QHBoxLayout,
    QWidget,
    QPushButton,
    QTextEdit,
)
from PyQt6.QtCore import QThread, pyqtSignal, QObject

import openai
import pygame
from openai import OpenAI

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


class TTSWorker(QObject):
    """Non-blocking worker for TTS generation and playback"""

    error_occurred = pyqtSignal(str)
    finished = pyqtSignal()
    chunk_generated = pyqtSignal(bytes)  # Signal when chunk audio is ready
    started = pyqtSignal()  # Signal when playback starts
    stopped = pyqtSignal()  # Signal when playback is stopped

    def __init__(self, api_key: str):
        super().__init__()
        self.client = OpenAI(api_key=api_key)
        self.chunker = SentenceChunker()
        self.is_stopping = False
        self.is_running = False
        self.audio_queue = queue.Queue()
        self.playback_thread = None

        # NEW: Queue for sequential chunk processing
        self.chunk_input_queue = queue.Queue()
        self.chunk_generation_thread = None

        # Initialize pygame mixer
        pygame.mixer.init(frequency=22050, size=-16, channels=2, buffer=512)

    def add_chunk(self, chunk_text: str):
        """Add a single chunk to the TTS queue - starts playback if not running"""
        if self.is_stopping:
            return

        # Start the system if this is the first chunk
        if not self.is_running:
            self._start_system()

        # Add chunk to input queue for sequential processing
        self.chunk_input_queue.put(chunk_text)

    def _start_system(self):
        """Initialize the playback system"""
        if self.is_running:
            return

        self.is_running = True
        self.is_stopping = False

        # Start chunk generation thread (NEW)
        self.chunk_generation_thread = threading.Thread(
            target=self._chunk_generation_worker, daemon=True
        )
        self.chunk_generation_thread.start()

        # Start playback thread
        self.playback_thread = threading.Thread(
            target=self._playback_worker, daemon=True
        )
        self.playback_thread.start()

        self.started.emit()

    def _chunk_generation_worker(self):
        """Background thread that processes chunks sequentially from the input queue"""
        while not self.is_stopping:
            try:
                # Get next chunk text (blocking with timeout)
                chunk_text = self.chunk_input_queue.get(timeout=1.0)

                if self.is_stopping:
                    break

                # Generate audio for this chunk
                audio_data = self._generate_audio(chunk_text)
                if audio_data is not None:
                    self.audio_queue.put(audio_data)
                    self.chunk_generated.emit(audio_data)

                # Mark task as done
                self.chunk_input_queue.task_done()

            except queue.Empty:
                # No chunks available, continue waiting
                continue
            except Exception as e:
                if not self.is_stopping:
                    self.error_occurred.emit(f"Chunk generation error: {str(e)}")
                break

    def _generate_single_chunk(self, chunk_text: str):
        """Generate audio for a single chunk and add to queue (DEPRECATED - kept for compatibility)"""
        # This method is now just a wrapper for add_chunk for backward compatibility
        self.add_chunk(chunk_text)

    def start_tts(self, text: str):
        """Start TTS processing - non-blocking"""
        self.is_stopping = False

        # Start the system
        self._start_system()

        # Start generation in a separate thread to avoid blocking
        generation_thread = threading.Thread(
            target=self._generate_chunks, args=(text,), daemon=True
        )
        generation_thread.start()

    def _generate_chunks(self, text: str):
        """Generate audio chunks in background thread"""
        try:
            # Create chunks
            chunks, _ = self.chunker.create_chunks(text, 3)
            if not chunks:
                self.error_occurred.emit("No text to process")
                return

            # Add chunks to sequential processing queue
            for chunk in chunks:
                if self.is_stopping:
                    break
                self.chunk_input_queue.put(chunk)

            # Signal end of generation after all chunks are processed
            # We'll wait for the chunk queue to be empty, then signal end
            self.chunk_input_queue.join()  # Wait for all chunks to be processed
            self.audio_queue.put(None)  # Sentinel value

        except Exception as e:
            self.error_occurred.emit(f"TTS Error: {str(e)}")

    def _generate_audio(self, text: str) -> Optional[bytes]:
        """Generate audio for a single chunk"""
        if self.is_stopping:
            return None

        try:
            response = self.client.audio.speech.create(
                model="gpt-4o-mini-tts",
                voice="alloy",
                input=text,
                speed=1.0,
                response_format="mp3",
            )
            return response.content
        except Exception as e:
            self.error_occurred.emit(f"Audio generation failed: {str(e)}")
            return None

    def _playback_worker(self):
        """Background thread for audio playback"""
        while not self.is_stopping:
            try:
                # Get next audio chunk (blocking with timeout)
                audio_data = self.audio_queue.get(timeout=1.0)

                if audio_data is None:  # Explicit end signal
                    break

                if self.is_stopping:
                    break

                # Play the audio chunk
                self._play_audio_chunk(audio_data)

            except queue.Empty:
                # No audio available, but keep running for streaming chunks
                if self.is_running:
                    continue
                else:
                    break
            except Exception as e:
                if not self.is_stopping:
                    self.error_occurred.emit(f"Playback error: {str(e)}")
                break

        self.is_running = False
        self.finished.emit()

    def _play_audio_chunk(self, audio_data: bytes):
        """Play a single audio chunk"""
        if self.is_stopping:
            return

        try:
            # Load audio data into pygame
            audio_file = io.BytesIO(audio_data)
            pygame.mixer.music.load(audio_file)
            pygame.mixer.music.play()

            # Wait for playback to complete (non-blocking check)
            while pygame.mixer.music.get_busy() and not self.is_stopping:
                time.sleep(0.05)  # Shorter sleep for more responsive stopping

        except Exception as e:
            if not self.is_stopping:
                raise e

    def stop(self):
        """Stop TTS generation and playback immediately"""
        self.is_stopping = True
        self.is_running = False

        # Stop current audio playback
        try:
            pygame.mixer.music.stop()
        except:
            pass

        # Clear both queues
        while not self.audio_queue.empty():
            try:
                self.audio_queue.get_nowait()
            except queue.Empty:
                break

        while not self.chunk_input_queue.empty():
            try:
                self.chunk_input_queue.get_nowait()
            except queue.Empty:
                break

        self.stopped.emit()
        self.finished.emit()


class SimpleTTSApp(QMainWindow):
    """Simple non-blocking TTS app for PyQt6"""

    def __init__(self):
        super().__init__()
        self.tts_worker = None
        self.tts_thread = None
        self.is_playing = False

        self.init_ui()

    def init_ui(self):
        self.setWindowTitle("Non-blocking Chunked TTS - PyQt6")
        self.setGeometry(100, 100, 600, 400)

        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        layout = QVBoxLayout(central_widget)

        # Text input
        self.text_input = QTextEdit()
        self.text_input.setPlainText(
            "This is a sample text for testing the chunked TTS system. "
            "It contains multiple sentences to demonstrate the chunking functionality. "
            "Dr. Smith said that the system should handle abbreviations like U.S.A. correctly. "
            "Each chunk will be processed separately for better performance. "
            "The interface should remain responsive during playback."
        )
        layout.addWidget(self.text_input)

        # Control buttons
        button_layout = QHBoxLayout()

        self.play_button = QPushButton("Play")
        self.play_button.clicked.connect(self.play_text)
        button_layout.addWidget(self.play_button)

        self.stop_button = QPushButton("Stop")
        self.stop_button.clicked.connect(self.stop_text)
        self.stop_button.setEnabled(False)
        button_layout.addWidget(self.stop_button)

        layout.addLayout(button_layout)

        # Add some padding
        layout.addStretch()

    def play_text(self):
        """Start playing the text - non-blocking"""
        if self.is_playing:
            return

        text = self.text_input.toPlainText().strip()
        if not text:
            return

        # Create worker and thread
        self.tts_thread = QThread()
        self.tts_worker = TTSWorker(api_key)
        self.tts_worker.moveToThread(self.tts_thread)

        # Connect signals
        self.tts_worker.error_occurred.connect(self.handle_error)
        self.tts_worker.finished.connect(self.on_playback_finished)
        self.tts_worker.stopped.connect(self.on_playback_finished)

        # Start the thread
        self.tts_thread.start()

        # Update UI state
        self.is_playing = True
        self.play_button.setEnabled(False)
        self.stop_button.setEnabled(True)

        # Start TTS processing (non-blocking)
        self.tts_worker.start_tts(text)

    def stop_text(self):
        """Stop playing the text immediately"""
        if not self.is_playing:
            return

        if self.tts_worker:
            self.tts_worker.stop()

    def handle_error(self, error_message: str):
        """Handle TTS errors"""
        print(f"Error: {error_message}")
        self.cleanup_worker()

    def on_playback_finished(self):
        """Called when playback is finished"""
        self.cleanup_worker()

    def cleanup_worker(self):
        """Clean up worker thread and reset UI"""
        self.is_playing = False
        self.play_button.setEnabled(True)
        self.stop_button.setEnabled(False)

        if self.tts_thread and self.tts_thread.isRunning():
            self.tts_thread.quit()
            self.tts_thread.wait(3000)  # Wait up to 3 seconds

        self.tts_worker = None
        self.tts_thread = None

    def closeEvent(self, event):
        """Handle application close"""
        if self.tts_worker:
            self.tts_worker.stop()

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
        print(f"Missing required package: {e}")
        print("Install with: pip install openai pygame")
        sys.exit(1)

    window = SimpleTTSApp()
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
