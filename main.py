from calendar import c
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
)
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QComboBox
import screen_grab, clipboard, TTS, asyncio, openai, os, json


class SidekickUI(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Sidekick")
        # Make the window always on top
        self.setWindowFlags(self.windowFlags() | Qt.WindowType.WindowStaysOnTopHint)
        self.init_ui()
        self.always_read = True

        conversation_path = "conversations/conversation.json"
        if os.path.exists(conversation_path):
            with open(conversation_path, "r", encoding="utf-8") as f:
                self.context = json.load(f)
        else:
            self.context = []

    def init_ui(self):
        main_layout = QVBoxLayout()

        # User Prompt Input section: contains the text input, send button, talk button, and context selection
        prompt_layout = QHBoxLayout()

        # Left: Prompt input
        self.prompt_input = QTextEdit()
        self.prompt_input.setPlaceholderText(
            "Type your prompt here..."
        )  # User types prompt here

        # Right: Vertical layout for buttons and context
        right_layout = QVBoxLayout()
        self.send_button = QPushButton("Send")  # Button to send prompt
        self.send_button.clicked.connect(
            self.on_send_button_clicked
        )  # Connect to handler
        self.talk_button = QPushButton(
            "Talk (Hold)"
        )  # Button for voice input (hold to talk)
        self.talk_button.setCheckable(False)

        self.context_combo = QComboBox()
        self.context_combo.addItems(
            ["No Context", "Clipboard", "Screenshot"]
        )  # Context options
        self.context_combo.setToolTip("Select context to add to your prompt")

        right_layout.addWidget(self.context_combo)
        right_layout.addWidget(self.send_button)
        right_layout.addWidget(self.talk_button)

        # Make the prompt_input match the height of the right_layout
        # We'll use a QWidget as a container for the right_layout to get its size
        right_widget = QWidget()
        right_widget.setLayout(right_layout)
        right_widget.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Fixed)

        self.prompt_input.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed
        )
        # Set minimum height of prompt_input to match the right_widget
        # We'll update the height after layout, but for now, set a reasonable minimum
        self.prompt_input.setMinimumHeight(80)
        right_widget.setMinimumHeight(80)

        prompt_layout.addWidget(self.prompt_input)
        prompt_layout.addWidget(right_widget)

        main_layout.addLayout(prompt_layout)

        # GPT Reply Display
        self.reply_display = QTextEdit()
        self.reply_display.setReadOnly(True)
        self.reply_display.setPlaceholderText("GPT reply will appear here...")
        main_layout.addWidget(self.reply_display)

        reply_actions_layout = QHBoxLayout()

        # Copy Button
        self.copy_reply_button = QPushButton("Copy Reply")
        reply_actions_layout.addWidget(self.copy_reply_button)
        self.copy_reply_button.clicked.connect(
            self.on_copy_reply_button_clicked
        )  # Connect to handler
        reply_actions_layout.addSpacerItem(
            QSpacerItem(
                40, 20, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum
            )
        )

        # Read Button
        self.read_button = QPushButton("Read")
        self.read_button.setCheckable(False)
        self.read_button.clicked.connect(self.on_read_button_clicked)

        reply_actions_layout.addWidget(self.read_button)

        main_layout.addLayout(reply_actions_layout)

        # Exit Button
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
        self.setMinimumWidth(400)

    # Define the send button handler
    def on_send_button_clicked(self):
        # Get the prompt text from the input field
        prompt_text = self.prompt_input.toPlainText()
        content = []
        content.append({"type": "input_text", "text": prompt_text})

        # Handle context selection: Screenshot or Clipboard
        if self.context_combo.currentText() == "Screenshot":
            # User chose to attach a screenshot
            img_url = screen_grab.grab_area_interactive()
            if img_url:
                # If the last input_text is empty, add a default question
                if not content[-1]["text"]:
                    content.append(
                        {"type": "input_text", "text": "What is in this image?"}
                    )
                # Attach the image to the message content
                content.append(openai.attach_image_message(img_url))
            # Clean up the temporary screenshot file
            screen_grab.cleanup_tempfile(img_url)
        elif self.context_combo.currentText() == "Clipboard":
            # User chose to attach clipboard text as context
            clipboard_text = clipboard.get_last_clipboard_text()
            if clipboard_text:
                content.append(
                    {"type": "input_text", "text": f"Context: {clipboard_text}"}
                )

        # Prepare the message for the OpenAI API
        messages = {"role": "user", "content": content}
        self.context.append(messages)
        print(self.context)
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
        reply_text = self.reply_display.toPlainText()
        clipboard.set_clipboard_text(reply_text)

    def on_read_button_clicked(self):
        reply_text = self.reply_display.toPlainText()
        asyncio.run(TTS.speak_async(reply_text))

    def print_context(self):
        print(self.context)

    def clear_context(self):
        self.context = []

    def save_conversation(self):
        with open("conversation_readable.txt", "w") as f:
            for message in self.context:
                f.write(f"{message["role"]}: {message["content"]}\n")
            f.write("\n")

        with open("conversations/conversation.json", "w", encoding="utf-8") as f:
            json.dump(self.context, f, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = SidekickUI()
    window.show()
    sys.exit(app.exec())
