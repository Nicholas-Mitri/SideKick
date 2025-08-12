import sys, datetime
from PyQt6.QtWidgets import (
    QApplication,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLineEdit,
    QTextEdit,
    QPushButton,
    QRadioButton,
    QLabel,
    QSpacerItem,
    QSizePolicy,
    QComboBox,
    QFileDialog,
)
from PyQt6.QtCore import (
    Qt,
    QPropertyAnimation,
    QEasingCurve,
    QParallelAnimationGroup,
    QTimer,
    QObject,
    QEvent,
)

import screen_grab
import clipboard
import TTS
import asyncio
import openai
import os
import json
import pygame
import time

import sounddevice as sd
import numpy as np
import threading
import tempfile
import wave


class PromptInputEventFilter(QObject):
    def __init__(self, parent):
        super().__init__(parent)
        self.parent = parent

    def eventFilter(self, obj, event):
        if event.type() == QEvent.Type.KeyPress:
            if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
                modifiers = QApplication.keyboardModifiers()
                # Only trigger if not holding Shift/Ctrl/Alt (i.e., plain Enter)
                if not (
                    modifiers
                    & (
                        Qt.KeyboardModifier.ShiftModifier
                        | Qt.KeyboardModifier.ControlModifier
                        | Qt.KeyboardModifier.AltModifier
                    )
                ):
                    TTS.clear()
                    self.parent.on_send_button_clicked()
                    return True  # suppress default
        return False


class SidekickUI(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Sidekick")
        # Keep the window always on top
        self.setWindowFlags(self.windowFlags() | Qt.WindowType.WindowStaysOnTopHint)

        # Initialize SidekickUI state variables
        self.websearch = False
        self.auto_read = True
        self.auto_grab = False
        self.right_widget_width = 140
        self.expand_at_start = False
        self.talk_button_height_after_expand = 30
        self.context = [
            {
                "role": "system",
                "content": [
                    {
                        "type": "input_text",
                        "text": f"{self.read_system_prompt()}",
                    }
                ],
            }
        ]
        self.init_ui()

    def init_ui(self):

        # Set minimum app width
        self.setMinimumWidth(100)
        main_layout = QVBoxLayout()
        # --- Top Row: Talk and Expand Buttons ---
        talk_layout = QHBoxLayout()
        self.talk_button = QPushButton("Talk (Hold)")  # Hold to talk (voice input)
        self.talk_button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.talk_button.pressed.connect(self.on_talk_button_pressed)
        self.talk_button.released.connect(self.on_talk_button_released)

        self.expand_button = QPushButton()
        self.expand_button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.expand_button.clicked.connect(self.on_expand_button_toggle)

        self.talk_button.setStyleSheet(
            """
            QPushButton {
                border-radius: 10px;
                color: white;
                background-color: #3498db;
                padding: 6px 10px;
            }
            QPushButton:hover {
                background-color: #2980b9;
            }
            QPushButton:pressed {
                background-color: #e74c3c; /* Record button red on press */
                color: white; /* White text for contrast */
            }
            """
        )

        self.expand_button.setStyleSheet(
            """
            QPushButton {
                border-radius: 10px;
                color: white;
                background-color: #3498db;
                padding: 6px 10px;
            }
            QPushButton:hover {
                background-color: #2980b9;
            }
            QPushButton:pressed {
                background-color: #2471a3;
            }
            """
        )
        if self.expand_at_start:
            self.expand_button.setFixedWidth(30)
            self.expand_button.setText("-")

        else:
            self.expand_button.setText("+")

            self.talk_button.setFixedSize(90, 60)
            self.expand_button.setFixedWidth(30)

            self.expand_button.setFixedHeight(self.talk_button.height())

            target_width = 180
            target_height = 100
            self.setMinimumSize(target_width, target_height)
            self.resize(target_width, target_height)

        talk_layout.addWidget(self.talk_button)
        talk_layout.addWidget(self.expand_button)
        main_layout.addLayout(talk_layout)

        # --- Prompt Input Section ---
        prompt_layout = QHBoxLayout()

        # Left: Prompt input field
        self.prompt_input = QTextEdit()
        self.prompt_input.setPlaceholderText("Type your prompt here...")

        self.prompt_input_event_filter = PromptInputEventFilter(self)
        self.prompt_input.installEventFilter(self.prompt_input_event_filter)

        # Right: Send button and context selection
        right_layout = QVBoxLayout()
        self.send_button = QPushButton("Send")
        self.send_button.clicked.connect(self.on_send_button_clicked)

        self.context_combo = QComboBox()
        self.context_combo.addItems(["No Context", "Clipboard", "Screenshot"])
        self.context_combo.setToolTip("Select context to add to your prompt")

        right_layout.addWidget(self.context_combo)
        right_layout.addWidget(self.send_button)

        # Container for right_layout to control its size
        right_widget = QWidget()
        right_widget.setLayout(right_layout)
        right_widget.setFixedWidth(self.right_widget_width)
        right_widget.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)

        self.prompt_input.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed
        )
        self.prompt_input.setMinimumHeight(80)
        right_widget.setMinimumHeight(80)

        prompt_layout.addWidget(self.prompt_input)
        prompt_layout.addWidget(right_widget)
        main_layout.addLayout(prompt_layout)

        # --- Reply and Options Section ---
        reply_and_options_layout = QHBoxLayout()

        # GPT reply display
        self.reply_display = QTextEdit()
        self.reply_display.setReadOnly(True)
        self.reply_display.setPlaceholderText("SideKick is thinking...")

        # Options: radio buttons, copy, read
        options_layout = QVBoxLayout()
        from PyQt6.QtWidgets import QCheckBox  # Ensure QCheckBox is imported

        self.checkbox_websearch = QCheckBox("Web Search")
        self.checkbox_websearch.setChecked(self.websearch)
        self.checkbox_websearch.stateChanged.connect(self.on_websearch_state_changed)
        self.checkbox_autograb = QCheckBox("Auto-Grab")
        self.checkbox_autograb.setChecked(self.auto_grab)
        self.checkbox_autograb.stateChanged.connect(self.on_autograb_state_changed)
        self.checkbox_autoread = QCheckBox("Auto-Read")
        self.checkbox_autoread.setChecked(self.auto_read)
        self.checkbox_autoread.stateChanged.connect(self.on_autoread_state_changed)

        self.copy_reply_button = QPushButton("Copy")
        self.copy_reply_button.clicked.connect(self.on_copy_reply_button_clicked)

        self.read_button = QPushButton("Read/Stop")
        self.read_button.clicked.connect(self.on_read_button_clicked)

        options_layout.addWidget(self.checkbox_websearch)
        options_layout.addWidget(self.checkbox_autograb)
        options_layout.addWidget(self.checkbox_autoread)
        options_layout.addWidget(self.copy_reply_button)
        options_layout.addWidget(self.read_button)

        reply_and_options_layout.addWidget(self.reply_display)

        options_widget = QWidget()
        options_widget.setLayout(options_layout)
        options_widget.setFixedWidth(self.right_widget_width)
        options_widget.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        options_widget.setFixedHeight(self.reply_display.sizeHint().height())
        reply_and_options_layout.addWidget(options_widget)

        main_layout.addLayout(reply_and_options_layout)

        # --- Exit Button Row ---
        exit_layout = QHBoxLayout()
        self.load_conversation_button = QPushButton("Load")
        self.load_conversation_button.clicked.connect(self.load_conversation)
        exit_layout.addWidget(self.load_conversation_button)

        self.save_conversation_button = QPushButton("Save")
        self.save_conversation_button.clicked.connect(self.save_conversation)
        exit_layout.addWidget(self.save_conversation_button)

        self.clear_context_button = QPushButton(
            f"Clear Context ({len(self.context)-1})"
        )
        self.clear_context_button.clicked.connect(self.clear_context)
        exit_layout.addWidget(self.clear_context_button)

        exit_layout.addSpacerItem(
            QSpacerItem(
                40, 20, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum
            )
        )
        self.exit_button = QPushButton("Exit")
        self.exit_button.clicked.connect(self.clear_and_exit)
        exit_layout.addWidget(self.exit_button)
        main_layout.addLayout(exit_layout)
        # INSERT_YOUR_CODE
        # Add a status bar at the bottom of the main layout
        self.status_bar = QLabel("Ready")
        self.status_bar.setStyleSheet("color: gray; padding: 2px 6px;")
        self.status_bar.setAlignment(
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
        )
        main_layout.addWidget(self.status_bar)

        self.setLayout(main_layout)
        self.set_app_start_mode()

    def on_send_button_clicked(self):
        """
        Handler for the Send button.
        Gathers the prompt and context, sends to OpenAI, and displays the reply.
        """

        self.talk_button.setStyleSheet(
            """
            QPushButton {
                border-radius: 10px;
                color: white;
                background-color:  #27ae60;
                padding: 6px 10px;
            }
            QPushButton:hover {
                background-color:  #27ae60;
            }
            QPushButton:pressed {
                background-color: #27ae60;
            }
            """
        )
        self.talk_button.setText("Thinking...")
        self.talk_button.repaint()
        QApplication.processEvents()
        print("Sending prompt...")
        prompt_text = self.prompt_input.toPlainText()
        content = [{"type": "input_text", "text": prompt_text}]

        # Handle context selection: Screenshot or Clipboard
        context_type = self.context_combo.currentText()
        if context_type == "Screenshot" or self.auto_grab:
            # Attach screenshot as context
            img_url = screen_grab.grab_area_interactive()
            if img_url:
                # If prompt is empty, add a default question for the image
                if not content[-1]["text"]:
                    content.append(
                        {"type": "input_text", "text": "What is in this image?"}
                    )
                content.append(openai.attach_image_message(img_url))
            # Clean up the temporary screenshot file
            screen_grab.cleanup_tempfile(img_url)
        elif context_type == "Clipboard":
            # Attach clipboard text as context
            clipboard_text = clipboard.get_last_clipboard_text()
            if clipboard_text:
                content.append(
                    {"type": "input_text", "text": f"Context: {clipboard_text}"}
                )

        # Prepare and send message to OpenAI
        messages = {"role": "user", "content": content}
        self.context.append(messages)
        reply = openai.chat_with_gpt5_stream(self.context, UI_object=self)
        reply = "".join(list(reply))
        self.context.append(
            {
                "role": "assistant",
                "content": [{"type": "output_text", "text": f"{reply}"}],
            }
        )
        self.clear_context_button.setText(f"Clear Context ({len(self.context)-1})")
        self.prompt_input.clear()

        self.talk_button.setStyleSheet(
            """
            QPushButton {
                border-radius: 10px;
                color: white;
                background-color: #3498db;
                padding: 6px 10px;
            }
            QPushButton:hover {
                background-color: #2980b9;
            }
            QPushButton:pressed {
                background-color: #e74c3c; /* Record button red on press */
                color: white; /* White text for contrast */
            }
            """
        )
        self.talk_button.setText("Talk (Hold)")
        self.talk_button.repaint()

    def on_copy_reply_button_clicked(self):
        """Copy the reply text to the clipboard."""
        reply_text = self.reply_display.toPlainText()
        clipboard.set_clipboard_text(reply_text)

    def on_read_button_clicked(self):
        # Check if audio is currently playing using pygame.mixer
        try:
            is_playing = pygame.mixer.get_init() and pygame.mixer.music.get_busy()
            print(f"Audio playing: {is_playing}")
        except Exception as e:
            print(f"Error checking audio playback: {e}")
            self.status_bar.setStyleSheet("color: red;")
            self.status_bar.setText("Error checking audio playback")
            QTimer.singleShot(3000, self.clear_status_bar)
            return

        if not is_playing:
            """Read the reply text aloud using TTS."""
            reply_text = self.reply_display.toPlainText()
            asyncio.run(TTS.speak_async(reply_text))

        else:
            # Stop audio playback if currently playing
            try:
                if pygame.mixer.get_init() and pygame.mixer.music.get_busy():
                    pygame.mixer.music.stop()
                    TTS.clear()
                    print("Audio playback stopped.")

            except Exception as e:
                print(f"Error stopping audio playback: {e}")

    def print_context(self):
        """Print the current conversation context to the console."""
        print(self.context)

    def clear_context(self):
        """Clear the conversation context."""
        self.context = [
            {
                "role": "system",
                "content": [
                    {
                        "type": "input_text",
                        "text": f"{self.read_system_prompt()}",
                    }
                ],
            }
        ]
        self.clear_context_button.setText(f"Clear Context ({len(self.context)-1})")

    def save_conversation(self):
        # Show a Qt file save dialog to let the user choose where to save the readable text file
        default_dir = os.path.join(os.getcwd(), "conversations")
        if not os.path.exists(default_dir):
            os.makedirs(default_dir)
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Save Conversation As",
            os.path.join(
                default_dir,
                f"conversation_{datetime.datetime.now().strftime('%Y-%m-%d')}.json",
            ),
            "JSON Files (*.json)",
        )
        print(file_path)
        if file_path:
            with open(file_path, "w", encoding="utf-8") as f:
                json.dump(self.context, f, ensure_ascii=False, indent=2)

    def load_conversation(self):
        # Show a Qt file open dialog to let the user pick a conversation JSON file from the conversations folder
        default_dir = os.path.join(os.getcwd(), "conversations")
        if not os.path.exists(default_dir):
            os.makedirs(default_dir)
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Load Conversation",
            default_dir,
            "JSON Files (*.json)",
        )
        if file_path:
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    self.context = json.load(f)
                    self.clear_context_button.setText(
                        f"Clear Context ({len(self.context)})"
                    )
            except Exception as e:
                print(f"Error loading conversation: {e}")
                self.status_bar.setStyleSheet("color: red;")
                self.status_bar.setText("Error Loading Conversation")
                QTimer.singleShot(3000, self.clear_status_bar)

    def on_expand_button_toggle(self):
        """
        Toggle between expanded and compact UI modes with animations.
        """
        # Disable UI while animations run to avoid clicks during geometry changes
        self.setEnabled(False)

        # Stop any previous animations and start a new group
        if hasattr(self, "anim_group") and self.anim_group is not None:
            try:
                self.anim_group.stop()
            except Exception:
                pass
        self.anim_group = QParallelAnimationGroup(self)

        if self.expand_at_start:
            # Collapse UI
            self.expand_at_start = False
            self.expand_button.setText("+")
            for widget in self.findChildren(QWidget):
                if widget is not self.talk_button and widget is not self.expand_button:
                    widget.hide()

            # Animate talk_button to compact size
            self.talk_button.setSizePolicy(
                QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Preferred
            )
            self.talk_button.setMaximumWidth(90)

            self.anim_h = QPropertyAnimation(self.talk_button, b"minimumHeight")
            self.anim_h.setDuration(300)
            self.anim_h.setStartValue(self.talk_button_height_after_expand)
            self.anim_h.setEndValue(60)
            self.anim_h.setEasingCurve(QEasingCurve.Type.OutCubic)
            self.anim_group.addAnimation(self.anim_h)

            self.anim_w = QPropertyAnimation(self.talk_button, b"minimumWidth")
            self.anim_w.setDuration(300)
            self.anim_w.setStartValue(self.talk_button.width())
            self.anim_w.setEndValue(90)
            self.anim_w.setEasingCurve(QEasingCurve.Type.OutCubic)
            self.anim_group.addAnimation(self.anim_w)

            # Animate expand button to compact height
            self.anime_h = QPropertyAnimation(self.expand_button, b"minimumHeight")
            self.anime_h.setDuration(300)
            self.anime_h.setStartValue(self.talk_button_height_after_expand)
            self.anime_h.setEndValue(60)
            self.anime_h.setEasingCurve(QEasingCurve.Type.OutCubic)
            self.anim_group.addAnimation(self.anime_h)

            # Animate app to compact size
            self.setSizePolicy(
                QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred
            )
            target_width = 180
            target_height = 100
            self.setMinimumSize(target_width, target_height)

            self.app_anim_h = QPropertyAnimation(self, b"maximumHeight")
            self.app_anim_h.setDuration(300)
            self.app_anim_h.setStartValue(self.height())
            self.app_anim_h.setEndValue(target_height)
            self.app_anim_h.setEasingCurve(QEasingCurve.Type.OutCubic)
            self.anim_group.addAnimation(self.app_anim_h)

            self.app_anim_w = QPropertyAnimation(self, b"maximumWidth")
            self.app_anim_w.setDuration(300)
            self.app_anim_w.setStartValue(self.width())
            self.app_anim_w.setEndValue(target_width)
            self.app_anim_w.setEasingCurve(QEasingCurve.Type.OutCubic)
            self.anim_group.addAnimation(self.app_anim_w)

        else:

            # Expand UI
            self.expand_at_start = True
            self.expand_button.setText("-")
            for widget in self.findChildren(QWidget):
                widget.show()

            # Animate talk_button to expanded size
            self.talk_button.setSizePolicy(
                QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred
            )
            self.talk_button.setMaximumWidth(900000)

            self.anim_h = QPropertyAnimation(self.talk_button, b"minimumHeight")
            self.anim_h.setDuration(300)
            self.anim_h.setStartValue(60)
            self.anim_h.setEndValue(self.talk_button_height_after_expand)
            self.anim_h.setEasingCurve(QEasingCurve.Type.OutCubic)
            self.anim_group.addAnimation(self.anim_h)

            # Animate expand button to expanded height
            self.anime_h = QPropertyAnimation(self.expand_button, b"minimumHeight")
            self.anime_h.setDuration(300)
            self.anime_h.setStartValue(60)
            self.anime_h.setEndValue(self.talk_button_height_after_expand)
            self.anime_h.setEasingCurve(QEasingCurve.Type.OutCubic)
            self.anim_group.addAnimation(self.anime_h)

            # Remove app size limits and animate to expanded size
            self.setMaximumSize(1000000, 1000000)
            self.setSizePolicy(
                QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Preferred
            )

            self.app_anim_h = QPropertyAnimation(self, b"minimumHeight")
            self.app_anim_h.setDuration(300)
            self.app_anim_h.setStartValue(self.height())
            self.app_anim_h.setEndValue(500)
            self.app_anim_h.setEasingCurve(QEasingCurve.Type.OutCubic)
            self.anim_group.addAnimation(self.app_anim_h)

            self.app_anim_w = QPropertyAnimation(self, b"minimumWidth")
            self.app_anim_w.setDuration(300)
            self.app_anim_w.setStartValue(self.width())
            self.app_anim_w.setEndValue(700)
            self.app_anim_w.setEasingCurve(QEasingCurve.Type.OutCubic)
            self.anim_group.addAnimation(self.app_anim_w)

        # Re-enable UI when all animations finish
        def _on_anims_finished():
            self.setEnabled(True)
            self.activateWindow()
            QApplication.processEvents()
            # Ensure pending events are processed post-animation
            QTimer.singleShot(0, QApplication.processEvents)

        self.anim_group.finished.connect(_on_anims_finished)
        self.anim_group.start()

    def set_app_start_mode(self):
        """
        Show or hide widgets based on the initial expand/collapse state.
        """
        if self.expand_at_start:
            for widget in self.findChildren(QWidget):
                widget.show()
        else:
            for widget in self.findChildren(QWidget):
                if widget is not self.talk_button and widget is not self.expand_button:
                    widget.hide()

    def on_talk_button_pressed(self):
        self.talk_button.setText("Listening...")
        self.audio_fs = 16000  # Sample rate
        self.audio_recording = True
        self.audio_frames = []

        def callback(indata, frames, time, status):
            if self.audio_recording:
                self.audio_frames.append(indata.copy())
            else:
                raise sd.CallbackStop()

        # Start recording in a thread to avoid blocking the UI
        def record_audio():
            with sd.InputStream(
                samplerate=self.audio_fs, channels=1, dtype="int16", callback=callback
            ):
                while self.audio_recording:
                    sd.sleep(50)

        self.audio_thread = threading.Thread(target=record_audio, daemon=True)
        self.audio_thread.start()

    def on_talk_button_released(self):
        print("Talk button released")
        self.talk_button.setStyleSheet(
            """
            QPushButton {
                border-radius: 10px;
                color: white;
                background-color:  #27ae60;
                padding: 6px 10px;
            }
            QPushButton:hover {
                background-color:  #27ae60;
            }
            QPushButton:pressed {
                background-color: #27ae60;
            }
            """
        )
        self.talk_button.setText("Thinking...")
        self.talk_button.repaint()

        print("Thinking...")
        QApplication.processEvents()
        # Stop recording
        self.audio_recording = False
        if hasattr(self, "audio_thread"):
            self.audio_thread.join()
        # Combine frames into a numpy array (optional: save or process)
        if hasattr(self, "audio_frames"):
            try:
                audio_data = np.concatenate(self.audio_frames, axis=0)
            except Exception as e:
                print(f"Error combining audio frames: {e}")
                self.status_bar.setStyleSheet("color: red;")
                self.status_bar.setText("Error Recording")
                QTimer.singleShot(3000, self.clear_status_bar)

                self.talk_button.setStyleSheet(
                    """
                QPushButton {
                    border-radius: 10px;
                    color: white;
                    background-color: #3498db;
                    padding: 6px 10px;
                }
                QPushButton:hover {
                    background-color: #2980b9;
                }
                QPushButton:pressed {
                    background-color: #e74c3c; /* Record button red on press */
                    color: white; /* White text for contrast */
                }
                """
                )
                self.clean_last_audio_tempfile()
                self.talk_button.setText("Talk (Hold)")
                return

            print(f"Recorded {len(audio_data)} samples.")

            # Save as WAV to a temporary file
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as wav_temp:
                with wave.open(wav_temp, "wb") as wf:
                    wf.setnchannels(1)
                    wf.setsampwidth(2)  # 16-bit audio
                    wf.setframerate(self.audio_fs)
                    wf.writeframes(audio_data.tobytes())
                self.last_audio_wav_path = wav_temp.name  # Store path for later use

            print(f"Audio saved as wav in tempfile: {self.last_audio_wav_path}")
            transcribed_text = openai.transcribe_audio(self.last_audio_wav_path)
            print(f"Transcribed text: {transcribed_text}")
            self.prompt_input.setText(transcribed_text)
            self.on_send_button_clicked()
            self.talk_button.setStyleSheet(
                """
                QPushButton {
                    border-radius: 10px;
                    color: white;
                    background-color: #3498db;
                    padding: 6px 10px;
                }
                QPushButton:hover {
                    background-color: #2980b9;
                }
                QPushButton:pressed {
                    background-color: #e74c3c; /* Record button red on press */
                    color: white; /* White text for contrast */
                }
                """
            )
            self.clean_last_audio_tempfile()
            self.talk_button.setText("Talk (Hold)")

    def clean_last_audio_tempfile(self):
        """
        Delete the last temporary audio file if it exists.
        """
        if hasattr(self, "last_audio_wav_path") and self.last_audio_wav_path:
            try:
                if os.path.exists(self.last_audio_wav_path):
                    os.remove(self.last_audio_wav_path)
                    print(f"Deleted tempfile: {self.last_audio_wav_path}")
                self.last_audio_wav_path = None
            except Exception as e:
                print(f"Error deleting tempfile: {e}")

    def clear_status_bar(self):
        self.status_bar.setText("")

    def on_websearch_state_changed(self, state):
        self.websearch = state == Qt.CheckState.Checked.value

    def on_autograb_state_changed(self, state):
        self.auto_grab = state == Qt.CheckState.Checked.value

    def on_autoread_state_changed(self, state):
        self.auto_read = state == Qt.CheckState.Checked.value

    def clear_and_exit(self):
        self.clear_context()
        self.close()

    def read_system_prompt(self):
        """Read the system prompt from a file."""
        if not os.path.exists("system_prompt.txt"):
            return ""
        with open("system_prompt.txt", "r") as f:
            return f.read()


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = SidekickUI()
    window.show()
    sys.exit(app.exec())
