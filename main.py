import sys
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
)
from PyQt6.QtCore import Qt, QPropertyAnimation, QEasingCurve

import screen_grab
import clipboard
import TTS
import asyncio
import openai
import os
import json

import sounddevice as sd
import numpy as np
import threading
import tempfile
import wave


class SidekickUI(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Sidekick")
        # Keep the window always on top
        self.setWindowFlags(self.windowFlags() | Qt.WindowType.WindowStaysOnTopHint)
        self.init_ui()
        self.always_read = True

        conversation_path = "conversations/conversation.json"
        if os.path.exists(conversation_path):
            with open(conversation_path, "r", encoding="utf-8") as f:
                try:
                    self.context = json.load(f)
                except json.JSONDecodeError:
                    self.context = [
                        {
                            "role": "system",
                            "content": [
                                {
                                    "type": "input_text",
                                    "text": "very brief to the point answers only.",
                                }
                            ],
                        }
                    ]
        else:
            self.context = [
                {
                    "role": "system",
                    "content": [
                        {
                            "type": "input_text",
                            "text": "very brief to the point answers only.",
                        }
                    ],
                }
            ]

    def init_ui(self):
        main_layout = QVBoxLayout()
        self.right_widget_width = 140
        self.expand_at_start = True
        self.talk_button_height_after_expand = 30

        # Set minimum app width
        self.setMinimumWidth(100)

        # --- Top Row: Talk and Expand Buttons ---
        talk_layout = QHBoxLayout()
        self.talk_button = QPushButton("Talk (Hold)")  # Hold to talk (voice input)
        self.talk_button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.talk_button.pressed.connect(self.on_talk_button_pressed)
        self.talk_button.released.connect(self.on_talk_button_released)

        self.expand_button = QPushButton()
        self.expand_button.setFixedWidth(30)
        self.expand_button.setText("-")
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

        talk_layout.addWidget(self.talk_button)
        talk_layout.addWidget(self.expand_button)
        main_layout.addLayout(talk_layout)

        # --- Prompt Input Section ---
        prompt_layout = QHBoxLayout()

        # Left: Prompt input field
        self.prompt_input = QTextEdit()
        self.prompt_input.setPlaceholderText("Type your prompt here...")

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
        self.reply_display.setPlaceholderText("GPT reply will appear here...")

        # Options: radio buttons, copy, read
        options_layout = QVBoxLayout()
        self.radio1 = QRadioButton("Option 1")
        self.radio2 = QRadioButton("Option 2")
        self.radio3 = QRadioButton("Option 3")

        self.copy_reply_button = QPushButton("Copy")
        self.copy_reply_button.clicked.connect(self.on_copy_reply_button_clicked)

        self.read_button = QPushButton("Read")
        self.read_button.clicked.connect(self.on_read_button_clicked)

        options_layout.addWidget(self.radio1)
        options_layout.addWidget(self.radio2)
        options_layout.addWidget(self.radio3)
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
        exit_layout.addSpacerItem(
            QSpacerItem(
                40, 20, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum
            )
        )
        self.exit_button = QPushButton("Exit App")
        self.exit_button.clicked.connect(self.save_conversation)
        exit_layout.addWidget(self.exit_button)
        main_layout.addLayout(exit_layout)

        self.setLayout(main_layout)
        self.set_app_start_mode()

    def on_send_button_clicked(self):
        """
        Handler for the Send button.
        Gathers the prompt and context, sends to OpenAI, and displays the reply.
        """
        prompt_text = self.prompt_input.toPlainText()
        content = [{"type": "input_text", "text": prompt_text}]

        # Handle context selection: Screenshot or Clipboard
        context_type = self.context_combo.currentText()
        if context_type == "Screenshot":
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
        reply = openai.chat_with_gpt5(self.context)
        self.context.append(
            {
                "role": "assistant",
                "content": [{"type": "output_text", "text": f"{reply}"}],
            }
        )

        # Display the reply in the UI
        self.reply_display.setPlainText(reply)

        # Optionally read the reply aloud if always_read is enabled
        if self.always_read:
            reply = self.reply_display.toPlainText()
            asyncio.run(TTS.speak_async(reply))

    def on_copy_reply_button_clicked(self):
        """Copy the reply text to the clipboard."""
        reply_text = self.reply_display.toPlainText()
        clipboard.set_clipboard_text(reply_text)

    def on_read_button_clicked(self):
        """Read the reply text aloud using TTS."""
        reply_text = self.reply_display.toPlainText()
        asyncio.run(TTS.speak_async(reply_text))

    def print_context(self):
        """Print the current conversation context to the console."""
        print(self.context)

    def clear_context(self):
        """Clear the conversation context."""
        self.context = []

    def save_conversation(self):
        """Save the conversation to a readable text file and a JSON file."""
        with open("conversation_readable.txt", "w") as f:
            for message in self.context:
                f.write(f"{message['role']}: {message['content']}\n")
            f.write("\n")

        with open("conversations/conversation.json", "w", encoding="utf-8") as f:
            json.dump(self.context, f, ensure_ascii=False, indent=2)

    def on_expand_button_toggle(self):
        """
        Toggle between expanded and compact UI modes with animations.
        """
        if self.expand_at_start:
            # Collapse UI
            self.expand_at_start = False
            self.expand_button.setText("+")
            for widget in self.findChildren(QWidget):
                if widget is not self.talk_button and widget is not self.expand_button:
                    widget.hide()

            self.talk_button.setStyleSheet(
                """
                QPushButton {
                    border-radius: 10px;
                    color: white;
                    background-color: #3498db;
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
                }
                QPushButton:hover {
                    background-color: #2980b9;
                }
                QPushButton:pressed {
                    background-color: #2471a3;
                }
                """
            )
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
            self.anim_h.start()

            self.anim_w = QPropertyAnimation(self.talk_button, b"minimumWidth")
            self.anim_w.setDuration(300)
            self.anim_w.setStartValue(self.talk_button.width())
            self.anim_w.setEndValue(90)
            self.anim_w.setEasingCurve(QEasingCurve.Type.OutCubic)
            self.anim_w.start()

            # Animate expand button to compact height
            self.anime_h = QPropertyAnimation(self.expand_button, b"minimumHeight")
            self.anime_h.setDuration(300)
            self.anime_h.setStartValue(self.talk_button_height_after_expand)
            self.anime_h.setEndValue(60)
            self.anime_h.setEasingCurve(QEasingCurve.Type.OutCubic)
            self.anime_h.start()

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
            self.app_anim_h.start()

            self.app_anim_w = QPropertyAnimation(self, b"maximumWidth")
            self.app_anim_w.setDuration(300)
            self.app_anim_w.setStartValue(self.width())
            self.app_anim_w.setEndValue(target_width)
            self.app_anim_w.setEasingCurve(QEasingCurve.Type.OutCubic)
            self.app_anim_w.start()

        else:

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
            self.anim_h.start()

            # Animate expand button to expanded height
            self.anime_h = QPropertyAnimation(self.expand_button, b"minimumHeight")
            self.anime_h.setDuration(300)
            self.anime_h.setStartValue(60)
            self.anime_h.setEndValue(self.talk_button_height_after_expand)
            self.anime_h.setEasingCurve(QEasingCurve.Type.OutCubic)
            self.anime_h.start()

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
            self.app_anim_h.start()

            self.app_anim_w = QPropertyAnimation(self, b"minimumWidth")
            self.app_anim_w.setDuration(300)
            self.app_anim_w.setStartValue(self.width())
            self.app_anim_w.setEndValue(700)
            self.app_anim_w.setEasingCurve(QEasingCurve.Type.OutCubic)
            self.app_anim_w.start()

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
        self.talk_button.setText("Talk (Hold)")
        # Stop recording
        self.audio_recording = False
        if hasattr(self, "audio_thread"):
            self.audio_thread.join()
        # Combine frames into a numpy array (optional: save or process)
        if hasattr(self, "audio_frames"):
            audio_data = np.concatenate(self.audio_frames, axis=0)
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
            self.clean_last_audio_tempfile()

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


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = SidekickUI()
    window.show()
    sys.exit(app.exec())
