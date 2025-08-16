import sys
import datetime, time
from PyQt6.QtCore import QObject, pyqtSignal, pyqtSlot
import os
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import (
    QApplication,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QTextEdit,
    QPushButton,
    QLabel,
    QSpacerItem,
    QSizePolicy,
    QFileDialog,
    QStyle,
)
from PyQt6.QtCore import (
    Qt,
    QPropertyAnimation,
    QEasingCurve,
    QParallelAnimationGroup,
    QTimer,
    QObject,
    QEvent,
    QThread,
)

import screen_grab
import clipboard
import openai_helper as openai
import os
import json
import pygame, requests

import sounddevice as sd
import numpy as np
import threading
import tempfile
import wave
import logging
import TTS_openai as TTS
import logging_config
import TTS_openai_streaming as TTS_S

logging_config.setup_root_logging("sidekick.log")
logger = logging.getLogger(__name__)


class GPTWorker(QObject):
    chunk = pyqtSignal(dict)  # stream text deltas
    done = pyqtSignal()  # finished successfully
    error = pyqtSignal(str)  # error message

    def __init__(self, content, tools=None):
        super().__init__()
        self._content = content
        self._tools = tools
        self._abort = False

    @pyqtSlot()
    def run(self):
        try:
            for obj in openai.chat_with_gpt5_stream(
                messages=self._content, tools=self._tools
            ):
                if self._abort:
                    break
                self.chunk.emit(obj)
            self.done.emit()
        except Exception as e:
            self.error.emit(str(e))

    def abort_now(self):
        self._abort = True

    def set_content(self, content):
        self._content = content

    def set_tools(self, tools):
        self._tools = tools


class PromptInputEventFilter(QObject):
    """Event filter to handle Enter key in prompt input."""

    def __init__(self, parent):
        """Initialize the event filter."""
        super().__init__(parent)
        self.parent = parent

    def eventFilter(self, obj, event):
        """Intercept Enter key to trigger send if no modifiers."""
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
                    # TTS.clear()
                    self.parent.on_send_button_clicked_nonblocking()
                    return True  # Suppress default
        return False


class SidekickUI(QWidget):
    """Main UI class for the Sidekick application."""

    def __init__(self):
        """Initialize the Sidekick UI and state."""
        super().__init__()
        self.setWindowTitle("Sidekick")
        # Keep the window always on top
        self.setWindowFlags(self.windowFlags() | Qt.WindowType.WindowStaysOnTopHint)

        self.mininumAnswerLength = 100
        self.clipboard = False
        self.screeshot = False
        self.websearch = False
        self.auto_read = False
        self.first_chunk = False
        self.screeshot_taken = False
        self.clipboard_taken = False
        self.expand_at_start = True

        self.img_url = ""
        self.clipboard_text = ""
        self.right_widget_width = 140
        self.talk_button_height_after_expand = 35
        self.collapsed_app_width = 200
        self.collapsed_app_height = 140
        self.expanded_app_width = 700
        self.expanded_app_height = 500

        self.setStyleSheet(
            """
            QWidget {
                background-color: #23272e;
                color: #f2f2f2;
                font-size: 14px;
                border: none;
            }
            QVBoxLayout, QHBoxLayout {
                background: transparent;
            }
            QTextEdit {
                background-color: #32363e;  /* A little lighter than #2a2e36 */
                border: 0px solid  #32363e;
                border-radius: 12px;
                padding: 10px;
                font-size: 14px;
                color: #f7f9fa;
                selection-background-color: #2d3a4a;
            }

            QLabel {
                color: #f2f2f2;
                font-size: 14px;
            }
            QCheckBox {
                color: #f2f2f2;
                font-size: 14px;
                spacing: 8px;
                padding: 2px 0 2px 0;
                background-color: #23272e;
            }
            QCheckBox::indicator {
                width: 18px;
                height: 18px;
                border-radius: 4px;
                border: 0px solid #444a58;
                background: #32363e;
            }
            QCheckBox::indicator:checked {
                background: #3498db;
                border: 0px solid #5a5f6e;
            }
            QCheckBox::indicator:unchecked {
                background: #32363e;
                border: 0px solid #444a58;
            }
            QPushButton {
                border-radius: 10px;
                color: #f2f2f2;
                background-color: #32363e;
                padding: 5px 9px;
                border: 0px solid #444a58;
                font-size: 13px;
            }
            QPushButton:hover {
                background-color: #31343b;
                border: 1px solid #5a5f6e;
            }
            QPushButton:pressed {
                background-color: #1a1d22;
                border: 1px solid #7b7f8a;
            }
            QPushButton:disabled {
                background-color: #32363e;
                color: #888;
                border: 1px solid #333;
            }
            QScrollBar:vertical, QScrollBar:horizontal {
                background: #23272e;
                border: none;
                width: 10px;
                margin: 0px 0px 0px 0px;
            }
            QScrollBar::handle:vertical, QScrollBar::handle:horizontal {
                background: #444a58;
                border-radius: 5px;
                min-height: 20px;
            }
            QScrollBar::add-line, QScrollBar::sub-line {
                background: none;
                border: none;
            }
        """
        )

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
        self.TALK_BUTTON_EXPANDED_DEFAULT_STYLE = """
                QPushButton {
                    border-radius: 10px;
                    color: white;
                    background-color: #3498db;
                    padding: 6px 14px;
                    font-size: 13px;
                }
                QPushButton:hover {
                    background-color: #2980b9;
                }
                QPushButton:pressed {
                    background-color: #e74c3c; /* Record button red on press */
                    color: white; /* White text for contrast */
                }
                """
        self.EXPAND_BUTTON_EXPANDED_DEFAULT_STYLE = """
                QPushButton {
                    border-radius: 10px;
                    color: white;
                    background-color: #3498db;
                    padding: 6px 14px;
                    font-size: 13px;

                }
                QPushButton:hover {
                    background-color: #2980b9;
                }
                QPushButton:pressed {
                    background-color: #2471a3;
                }
                """
        self.TALK_BUTTON_COLLAPSED_DEFAULT_STYLE = """
                QPushButton {
                    border-radius: 20px;
                    color: white;
                    background-color: #3498db;
                    padding: 6px 14px;
                    font-size: 13px;
                }
                QPushButton:hover {
                    background-color: #2980b9;
                }
                QPushButton:pressed {
                    background-color: #e74c3c; /* Record button red on press */
                    color: white; /* White text for contrast */
                }
                """
        self.EXPAND_BUTTON_COLLAPSED_DEFAULT_STYLE = """
                QPushButton {
                    border-radius: 20px;
                    color: white;
                    background-color: #3498db;
                    padding: 6px 14px;
                    font-size: 13px;

                }
                QPushButton:hover {
                    background-color: #2980b9;
                }
                QPushButton:pressed {
                    background-color: #2471a3;
                }
                """
        self.TALK_BUTTON_EXPANDED_LISTENING_STYLE = """
                QPushButton {
                    border-radius: 10px;
                    color: white;
                    background-color: #e74c3c; /* Record button red */
                    padding: 6px 14px;
                    font-size: 13px;
                }
                QPushButton:hover {
                    background-color: #c0392b; /* Darker red on hover */
                }
                QPushButton:pressed {
                    background-color: #a93226; /* Even darker red on press */
                    color: white; /* White text for contrast */
                }
                """
        self.TALK_BUTTON_EXPANDED_INTERRUPT_STYLE = """
                QPushButton {
                    border-radius: 10px;
                    color: white;
                    background-color: orange;
                    padding: 6px 14px;
                    font-size: 13px;
                }
                QPushButton:hover {
                    background-color: darkorange;
                }
                QPushButton:pressed {
                    background-color: #ff9800; /* Deeper orange on press */
                    color: white; /* White text for contrast */
                }
                """
        self.TALK_BUTTON_COLLAPSED_LISTENING_STYLE = """
                QPushButton {
                    border-radius: 20px;
                    color: white;
                    background-color: #e74c3c; /* Record button red */
                    padding: 6px 14px;
                    font-size: 13px;
                }
                QPushButton:hover {
                    background-color: #c0392b; /* Darker red on hover */
                }
                QPushButton:pressed {
                    background-color: #a93226; /* Even darker red on press */
                    color: white; /* White text for contrast */
                }
                """
        self.TALK_BUTTON_COLLAPSED_INTERRUPT_STYLE = """
                QPushButton {
                    border-radius: 20px;
                    color: white;
                    background-color: orange;
                    padding: 6px 14px;
                    font-size: 13px;
                }
                QPushButton:hover {
                    background-color: darkorange;
                }
                QPushButton:pressed {
                    background-color: #ff9800; /* Deeper orange on press */
                    color: white; /* White text for contrast */
                }
                """
        self.COLLAPSED_BUTTONS_DEFAULT_STYLE = """
                QPushButton {
                    border-radius: 12px;
                    color: white;
                    background-color: #3498db;
                    padding: 6px 14px;
                    font-size: 13px;

                }
                QPushButton:hover {
                    background-color: #2980b9;
                }
                QPushButton:pressed {
                    background-color: #2471a3;
                }
                """
        # Create worker + thread
        self.gpt_thread = None
        self.gpt_worker = None

        self.streaming_reply = ""
        self.citations = dict()
        self.partial_transciption = ""
        self.init_tts_service()
        self.chunker = TTS_S.SentenceChunker()
        self.init_ui()

    def init_ui(self):
        """Set up the UI layout and widgets."""
        # Set minimum app width
        main_layout = QVBoxLayout()

        # Create a QWidget with QVBoxLayout and three buttons with placeholder icons, hidden by default
        collapsed_buttons_layout = QHBoxLayout()
        # Create three buttons with placeholder icons
        self.collapsed_screenshot_button = QPushButton()
        self.collapsed_screenshot_button.setStyleSheet(
            self.COLLAPSED_BUTTONS_DEFAULT_STYLE
        )
        self.collapsed_screenshot_button.clicked.connect(
            self.on_screenshot_button_clicked
        )
        self.collapsed_screenshot_button.setToolTip("Take a screenshot")
        self.collapsed_clipboard_button = QPushButton()
        self.collapsed_clipboard_button.setStyleSheet(
            self.COLLAPSED_BUTTONS_DEFAULT_STYLE
        )
        self.collapsed_clipboard_button.clicked.connect(
            self.on_clipboard_button_clicked
        )
        self.collapsed_clipboard_button.setToolTip("Copy from clipboard")
        self.collapsed_read_button = QPushButton()
        self.collapsed_read_button.setStyleSheet(self.COLLAPSED_BUTTONS_DEFAULT_STYLE)
        self.collapsed_read_button.clicked.connect(
            self.on_read_button_clicked_streaming
        )
        self.collapsed_read_button.setToolTip("Start/Stop reading")

        # Define paths to your custom icons
        screenshot_icon_path = (
            "icons/screenshot_region_24dp_FFFFFF_FILL0_wght400_GRAD0_opsz24.svg"
        )
        clipboard_icon_path = (
            "icons/content_copy_24dp_FFFFFF_FILL0_wght400_GRAD0_opsz24.svg"
        )
        read_icon_path = "icons/autostop_24dp_FFFFFF_FILL0_wght400_GRAD0_opsz24.svg"

        # Screenshot button icon
        if os.path.exists(screenshot_icon_path):
            self.collapsed_screenshot_button.setIcon(QIcon(screenshot_icon_path))
        else:
            self.collapsed_screenshot_button.setIcon(
                self.style().standardIcon(QStyle.StandardPixmap.SP_DesktopIcon)
            )

        # Clipboard button icon
        if os.path.exists(clipboard_icon_path):
            self.collapsed_clipboard_button.setIcon(QIcon(clipboard_icon_path))
        else:
            self.collapsed_clipboard_button.setIcon(
                self.style().standardIcon(QStyle.StandardPixmap.SP_DialogSaveButton)
            )

        # Read button icon
        if os.path.exists(read_icon_path):
            self.collapsed_read_button.setIcon(QIcon(read_icon_path))
        else:
            self.collapsed_read_button.setIcon(
                self.style().standardIcon(QStyle.StandardPixmap.SP_MediaPlay)
            )

        # Add buttons to the layout
        collapsed_buttons_layout.addWidget(self.collapsed_screenshot_button)
        collapsed_buttons_layout.addWidget(self.collapsed_clipboard_button)
        collapsed_buttons_layout.addWidget(self.collapsed_read_button)

        main_layout.addLayout(collapsed_buttons_layout)

        # Talk button row
        talk_layout = QHBoxLayout()

        # Talk button for voice input
        self.talk_button = QPushButton("Talk (Hold)")
        self.talk_button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.talk_button.pressed.connect(self.on_talk_button_pressed)
        self.talk_button.released.connect(self.on_talk_button_released)
        self.talk_button.setToolTip("Hold to record. Click to interrupt reply.")

        # Expand/collapse button
        self.expand_button = QPushButton()
        self.expand_button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.expand_button.clicked.connect(self.on_expand_button_toggle)
        self.expand_button.setToolTip("Expand/Collapse")

        # Set initial expand/collapse state
        if self.expand_at_start:
            # Style for talk button
            self.talk_button.setStyleSheet(self.TALK_BUTTON_EXPANDED_DEFAULT_STYLE)

            # Style for expand button
            self.expand_button.setStyleSheet(self.EXPAND_BUTTON_EXPANDED_DEFAULT_STYLE)
            self.expand_button.setFixedWidth(40)
            self.expand_button.setText("-")
            self.resize(self.expanded_app_width, self.expanded_app_height)

        else:
            # Style for talk button
            self.talk_button.setStyleSheet(self.EXPAND_BUTTON_COLLAPSED_DEFAULT_STYLE)

            # Style for expand button
            self.expand_button.setStyleSheet(self.EXPAND_BUTTON_COLLAPSED_DEFAULT_STYLE)
            self.expand_button.setText("+")
            self.talk_button.setFixedSize(100, 60)
            self.expand_button.setFixedWidth(40)
            self.expand_button.setFixedHeight(self.talk_button.height())

            self.setMinimumSize(self.collapsed_app_width, self.collapsed_app_height)
            self.resize(self.collapsed_app_width, self.collapsed_app_height)

        talk_layout.addWidget(self.talk_button)
        talk_layout.addWidget(self.expand_button)
        main_layout.addLayout(talk_layout)

        # --- Prompt Input Section ---
        prompt_layout = QHBoxLayout()

        # Left: Prompt input field
        self.prompt_input = QTextEdit()
        self.prompt_input.setPlaceholderText("Type your prompt [Enter to send]...")
        # Style is now set app-wide

        # Install event filter for Enter key
        self.prompt_input_event_filter = PromptInputEventFilter(self)
        self.prompt_input.installEventFilter(self.prompt_input_event_filter)

        # Right: Send button
        right_layout = QVBoxLayout()
        self.screenshot_button = QPushButton("+ Screenshot")
        self.screenshot_button.clicked.connect(self.on_screenshot_button_clicked)
        self.screenshot_button.setToolTip("Take a screenshot")
        self.clipboard_button = QPushButton("+ Clipboard")
        self.clipboard_button.clicked.connect(self.on_clipboard_button_clicked)
        self.clipboard_button.setToolTip("Copy from clipboard")
        self.send_button = QPushButton("Send")
        self.send_button.clicked.connect(self.on_send_button_clicked_nonblocking)
        self.send_button.setToolTip("Send prompt")

        right_layout.addWidget(self.screenshot_button)
        right_layout.addWidget(self.clipboard_button)
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
        self.reply_display.setPlaceholderText("SideKick will reply here...")
        # Style is now set app-wide

        # Options: checkboxes, copy, read
        options_layout = QVBoxLayout()
        from PyQt6.QtWidgets import QCheckBox  # Ensure QCheckBox is imported

        # Web search context checkbox
        self.checkbox_websearch = QCheckBox("Web Search")
        self.checkbox_websearch.setChecked(self.websearch)
        self.checkbox_websearch.setEnabled(False)
        self.checkbox_websearch.stateChanged.connect(self.on_websearch_state_changed)
        self.checkbox_websearch.setToolTip("Enable web search.")

        # Auto-read reply checkbox
        self.checkbox_autoread = QCheckBox("Auto-Read")
        self.checkbox_autoread.setChecked(self.auto_read)
        self.checkbox_autoread.stateChanged.connect(self.on_autoread_state_changed)
        self.checkbox_autoread.setToolTip("Enable auto-read on reply.")

        # Copy reply button
        self.copy_reply_button = QPushButton("Copy")
        self.copy_reply_button.clicked.connect(self.on_copy_reply_button_clicked)
        self.copy_reply_button.setToolTip("Copy reply to clipboard.")

        # Read/Stop TTS button
        self.read_button = QPushButton("Read/Stop")
        self.read_button.clicked.connect(self.on_read_button_clicked_streaming)
        self.read_button.setToolTip("Read/Stop reply.")

        # Add all options to layout
        options_layout.addWidget(self.checkbox_websearch)
        options_layout.addWidget(self.checkbox_autoread)
        options_layout.addWidget(self.copy_reply_button)
        options_layout.addWidget(self.read_button)

        reply_and_options_layout.addWidget(self.reply_display)

        # Options widget container
        options_widget = QWidget()
        options_widget.setLayout(options_layout)
        options_widget.setFixedWidth(self.right_widget_width)
        options_widget.setSizePolicy(
            QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Expanding
        )
        reply_and_options_layout.addWidget(options_widget)

        main_layout.addLayout(reply_and_options_layout)

        # --- Exit Button Row ---
        context_options_layout = QHBoxLayout()
        # Load conversation button
        self.load_conversation_button = QPushButton("Load")
        self.load_conversation_button.clicked.connect(self.load_conversation)
        self.load_conversation_button.setToolTip("Load conversation (JSON) from file.")
        context_options_layout.addWidget(self.load_conversation_button)

        # Save conversation button
        self.save_conversation_button = QPushButton("Save")
        self.save_conversation_button.clicked.connect(self.save_conversation)
        self.save_conversation_button.setToolTip("Save conversation to JSON.")
        context_options_layout.addWidget(self.save_conversation_button)

        # Clear context button
        self.clear_context_button = QPushButton(
            f"Clear Context ({len(self.context)-1})"
        )
        self.clear_context_button.clicked.connect(self.clear_context)
        self.clear_context_button.setToolTip(
            "Clear conversation context. (#) indicates number of messages saved in context."
        )

        context_options_layout.addWidget(self.clear_context_button)

        # Spacer and Exit button
        context_options_layout.addSpacerItem(
            QSpacerItem(
                40, 20, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum
            )
        )
        main_layout.addLayout(context_options_layout)

        # Exit button
        exit_layout = QHBoxLayout()
        self.exit_button = QPushButton("Exit")
        self.exit_button.clicked.connect(self.clear_and_exit)
        self.exit_button.setFixedWidth(80)

        # Add a status bar at the bottom of the main layout
        self.status_bar = QLabel("Ready")
        self.status_bar.setStyleSheet("color: gray; padding: 2px 6px;")
        self.update_status_bar(text="Ready", color="gray", timer=-1)
        self.status_bar.setAlignment(
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
        )
        exit_layout.addWidget(self.status_bar)
        exit_layout.addWidget(self.exit_button)
        main_layout.addLayout(exit_layout)

        self.setLayout(main_layout)
        self.set_app_start_mode()

        # Disable app if no OpenAI API key
        if not openai.OPENAI_API_KEY:
            if not self.expand_at_start:
                self.on_expand_button_toggle()

            self.update_status_bar(
                text="No OpenAI API Key! App disabled!",
                color="red",
                timer=-1,
            )
            self.setEnabled(False)

        # Check API key
        self.check_api_key()

    def update_status_bar(self, text="Ready", color="gray", timer=-1):
        """Update the status bar text and color."""
        logger.info(f"Updating status bar to: {text}")
        self.status_bar.setText(text)
        self.status_bar.setStyleSheet(f"color: {color}")
        if timer > -1:
            QTimer.singleShot(timer, self.clear_status_bar)

    def clear_status_bar(self):
        self.update_status_bar(text="Ready", color="gray", timer=-1)

    def on_gpt_error(self, error):
        logger.error(f"Received error: {error}")
        self.first_chunk = False
        self.update_status_bar(f"Error occured. Please check log.", "red", 3000)
        # Re-enable the send button on error
        self.send_button.setEnabled(True)
        self.prompt_input.setEnabled(True)
        self.cleanup_gpt_thread()

    def on_gpt_abort(self, abort):
        logger.info(f"Received abort: {abort}")
        self.update_status_bar("Aborting previous prompt...", "red", 3000)
        # Re-enable the send button on abort
        self.send_button.setEnabled(True)
        self.prompt_input.setEnabled(True)

    def update_talk_button(self, text="", styleSheet=None):
        self.talk_button.setText(text)
        self.talk_button.setStyleSheet(styleSheet)
        self.talk_button.repaint()
        QApplication.processEvents()

    def format_web_reply(self, reply, citations):
        if len(citations) == 0:
            return reply
        citation_block = "Citations:\n"
        sorted_citations = sorted(citations.items(), key=lambda x: x[1]["order"])
        for c in sorted_citations:
            citation_block += f"[{c[1]['order']}]: ({c[1]['url']}) {c[1]['title']}\n"
        return f"{reply}\n\n{citation_block}"

    def on_screenshot_button_clicked(self):
        self.img_url = screen_grab.grab_area_interactive()
        if self.img_url:
            self.update_status_bar(
                text="Screenshot added to context",
                color="green",
                timer=3000,
            )
            self.screeshot_taken = True
        else:
            self.update_status_bar(
                text="Failed to add screenshot to context",
                color="red",
                timer=3000,
            )
            self.screeshot_taken = False

    def on_clipboard_button_clicked(self):
        self.clipboard_text = clipboard.get_last_clipboard_text()
        if self.clipboard_text:
            self.update_status_bar(
                text="Clipboard added to context",
                color="green",
                timer=3000,
            )
            self.clipboard_taken = True
        else:
            self.update_status_bar(
                text="Failed to add clipboard to context",
                color="red",
                timer=3000,
            )
            self.clipboard_taken = False

    def on_copy_reply_button_clicked(self):
        """Copy the reply text to the clipboard."""
        reply_text = self.reply_display.toPlainText()
        if clipboard.set_clipboard_text(reply_text):
            self.update_status_bar(
                text="Reply copied to clipboard",
                color="green",
                timer=3000,
            )
        else:
            self.update_status_bar(
                text="Failed to copy reply to clipboard",
                color="red",
                timer=3000,
            )

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
        """Save the current conversation to a file."""
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
        """Load a conversation from a file."""
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
                self.update_status_bar(
                    text="Error Loading Conversation",
                    color="red",
                    timer=-1,
                )

    def on_expand_button_toggle(self):
        """Toggle between expanded and compact UI modes with animations."""
        # Stop any previous animations and start a new group
        if hasattr(self, "anim_group") and self.anim_group is not None:
            try:
                self.anim_group.stop()
            except Exception:
                pass
        self.anim_group = QParallelAnimationGroup(self)

        if self.expand_at_start:
            # Collapse UI

            # Style for talk button
            self.talk_button.setStyleSheet(self.TALK_BUTTON_COLLAPSED_DEFAULT_STYLE)

            # Style for expand button
            self.expand_button.setStyleSheet(self.EXPAND_BUTTON_COLLAPSED_DEFAULT_STYLE)

            self.expand_at_start = False
            self.expand_button.setText("+")
            for widget in self.findChildren(QWidget):
                if widget not in [
                    self.talk_button,
                    self.expand_button,
                    self.collapsed_clipboard_button,
                    self.collapsed_screenshot_button,
                    self.collapsed_read_button,
                ]:
                    widget.hide()
                else:
                    widget.show()

            self.talk_button.setMaximumWidth(120)

            self.anim_h = QPropertyAnimation(self.talk_button, b"minimumHeight")
            self.anim_h.setDuration(300)
            self.anim_h.setStartValue(self.talk_button_height_after_expand)
            self.anim_h.setEndValue(60)
            self.anim_h.setEasingCurve(QEasingCurve.Type.OutCubic)
            self.anim_group.addAnimation(self.anim_h)

            self.anim_w = QPropertyAnimation(self.talk_button, b"minimumWidth")
            self.anim_w.setDuration(300)
            self.anim_w.setStartValue(self.talk_button.width())
            self.anim_w.setEndValue(100)
            self.anim_w.setEasingCurve(QEasingCurve.Type.OutCubic)
            self.anim_group.addAnimation(self.anim_w)

            # Animate expand button to compact height
            self.anime_h = QPropertyAnimation(self.expand_button, b"minimumHeight")
            self.anime_h.setDuration(300)
            self.anime_h.setStartValue(self.talk_button_height_after_expand)
            self.anime_h.setEndValue(60)
            self.anime_h.setEasingCurve(QEasingCurve.Type.OutCubic)
            self.anim_group.addAnimation(self.anime_h)

            self.setMinimumSize(self.collapsed_app_width, self.collapsed_app_height)

            self.app_anim_h = QPropertyAnimation(self, b"maximumHeight")
            self.app_anim_h.setDuration(300)
            self.app_anim_h.setStartValue(self.height())
            self.app_anim_h.setEndValue(self.collapsed_app_height)
            self.app_anim_h.setEasingCurve(QEasingCurve.Type.OutCubic)
            self.anim_group.addAnimation(self.app_anim_h)

            self.app_anim_w = QPropertyAnimation(self, b"maximumWidth")
            self.app_anim_w.setDuration(300)
            self.app_anim_w.setStartValue(self.width())
            self.app_anim_w.setEndValue(self.collapsed_app_width)
            self.app_anim_w.setEasingCurve(QEasingCurve.Type.OutCubic)
            self.anim_group.addAnimation(self.app_anim_w)

            # Move the window to the top right corner of the screen
            screen = QApplication.primaryScreen()
            if screen:
                screen_geometry = screen.availableGeometry()
                window_width = self.collapsed_app_width
                x = screen_geometry.x() + screen_geometry.width() - window_width - 20
                y = screen_geometry.y() + 20
                self.move(x, y)
        else:
            # Expand UI
            # Style for talk button
            self.talk_button.setStyleSheet(self.TALK_BUTTON_EXPANDED_DEFAULT_STYLE)

            # Style for expand button
            self.expand_button.setStyleSheet(self.EXPAND_BUTTON_EXPANDED_DEFAULT_STYLE)
            self.expand_at_start = True
            self.expand_button.setText("-")
            for widget in self.findChildren(QWidget):
                if widget not in [
                    self.collapsed_clipboard_button,
                    self.collapsed_screenshot_button,
                    self.collapsed_read_button,
                ]:
                    widget.show()
                else:
                    widget.hide()

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

            self.setMaximumSize(self.expanded_app_width, self.expanded_app_height)

            self.app_anim_h = QPropertyAnimation(self, b"minimumHeight")
            self.app_anim_h.setDuration(300)
            self.app_anim_h.setStartValue(self.height())
            self.app_anim_h.setEndValue(self.expanded_app_height)
            self.app_anim_h.setEasingCurve(QEasingCurve.Type.OutCubic)
            self.anim_group.addAnimation(self.app_anim_h)

            self.app_anim_w = QPropertyAnimation(self, b"minimumWidth")
            self.app_anim_w.setDuration(300)
            self.app_anim_w.setStartValue(self.width())
            self.app_anim_w.setEndValue(self.expanded_app_width)
            self.app_anim_w.setEasingCurve(QEasingCurve.Type.OutCubic)
            self.anim_group.addAnimation(self.app_anim_w)

            # Move the window to the center of the screen after expanding
            screen = QApplication.primaryScreen()
            if screen:
                screen_geometry = screen.availableGeometry()
                x = (
                    screen_geometry.x()
                    + (screen_geometry.width() - self.expanded_app_width) // 2
                )
                y = (
                    screen_geometry.y()
                    + (screen_geometry.height() - self.expanded_app_height) // 2
                )
                self.move(x, y)

        # Re-enable UI when all animations finish
        def _on_anims_finished():
            self.activateWindow()  # Ensure pending events are processed post-animation
            (
                QTimer.singleShot(10, self.prompt_input.setFocus)
                if self.expand_at_start
                else QTimer.singleShot(10, self.talk_button.setFocus)
            )
            (
                QTimer.singleShot(
                    0,
                    lambda: self.setFixedSize(
                        self.expanded_app_width, self.expanded_app_height
                    ),
                )
                if self.expand_at_start
                else QTimer.singleShot(
                    0,
                    lambda: self.setFixedSize(
                        self.collapsed_app_width, self.collapsed_app_height
                    ),
                )
            )

        self.anim_group.finished.connect(_on_anims_finished)
        self.anim_group.start()

    def set_app_start_mode(self):
        """Show or hide widgets based on the initial expand/collapse state."""
        if self.expand_at_start:
            for widget in self.findChildren(QWidget):
                if widget not in [
                    self.collapsed_clipboard_button,
                    self.collapsed_screenshot_button,
                    self.collapsed_read_button,
                ]:
                    widget.show()
                else:
                    widget.hide()

                    # Move the window to the center of the screen after expanding
            screen = QApplication.primaryScreen()
            if screen:
                screen_geometry = screen.availableGeometry()
                x = (
                    screen_geometry.x()
                    + (screen_geometry.width() - self.expanded_app_width) // 2
                )
                y = (
                    screen_geometry.y()
                    + (screen_geometry.height() - self.expanded_app_height) // 2
                )
                self.move(x, y)
        else:
            for widget in self.findChildren(QWidget):
                if widget not in [
                    self.talk_button,
                    self.expand_button,
                    self.collapsed_clipboard_button,
                    self.collapsed_screenshot_button,
                    self.collapsed_read_button,
                ]:
                    widget.hide()
                else:
                    widget.show()

            # Move the window to the top right corner of the screen
            screen = QApplication.primaryScreen()
            if screen:
                screen_geometry = screen.availableGeometry()
                window_width = self.collapsed_app_width
                x = screen_geometry.x() + screen_geometry.width() - window_width - 20
                y = screen_geometry.y() + 20
                self.move(x, y)

    def on_talk_button_pressed(self):

        if self.gpt_thread:
            if self.gpt_thread.isRunning():
                return
        else:
            """Start recording audio for voice input."""
            # TTS.clear()
            logger.debug("Talk button pressed")
            self.update_status_bar(
                text="Listening...",
                timer=-1,
            )
            style = (
                self.TALK_BUTTON_EXPANDED_LISTENING_STYLE
                if self.expand_at_start
                else self.TALK_BUTTON_COLLAPSED_LISTENING_STYLE
            )
            self.update_talk_button("Listening...", styleSheet=style)
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
                    samplerate=self.audio_fs,
                    channels=1,
                    dtype="int16",
                    callback=callback,
                ):
                    while self.audio_recording:
                        sd.sleep(50)

            self.audio_thread = threading.Thread(target=record_audio, daemon=True)
            self.audio_thread.start()

    def on_talk_button_released(self):

        if self.gpt_thread:
            if self.gpt_thread.isRunning():
                logger.info("GPT detected as already running and interrupted!")
                self.gpt_worker.abort_now()
                return

        self.talk_button.setEnabled(False)

        # Stop recording
        self.audio_recording = False
        if hasattr(self, "audio_thread"):
            self.audio_thread.join()
        # Combine frames into a numpy array (optional: save or process)
        if hasattr(self, "audio_frames"):
            try:
                audio_data = np.concatenate(self.audio_frames, axis=0)
            except Exception as e:
                logger.error(f"Error combining audio frames: {e}")
                self.update_status_bar(
                    text="Error Recording",
                    color="red",
                    timer=3000,
                )
                style = (
                    self.TALK_BUTTON_EXPANDED_DEFAULT_STYLE
                    if self.expand_at_start
                    else self.TALK_BUTTON_COLLAPSED_DEFAULT_STYLE
                )
                self.update_talk_button("Talk (Hold)", styleSheet=style)
                self.clean_last_audio_tempfile()
                return

            logger.debug(f"Recorded {len(audio_data)} samples.")

            # Save as WAV to a temporary file
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as wav_temp:
                with wave.open(wav_temp, "wb") as wf:
                    wf.setnchannels(1)
                    wf.setsampwidth(2)  # 16-bit audio
                    wf.setframerate(self.audio_fs)
                    wf.writeframes(audio_data.tobytes())
                self.last_audio_wav_path = wav_temp.name  # Store path for later use

            logger.debug(f"Audio saved as wav in tempfile: {self.last_audio_wav_path}")
            try:
                transcribed_text = openai.transcribe_audio(self.last_audio_wav_path)
            except Exception as e:
                logger.error(f"Error transcribing audio: {e}")
                self.update_status_bar(
                    text="Error Transcribing",
                    color="red",
                    timer=3000,
                )
                style = (
                    self.TALK_BUTTON_EXPANDED_DEFAULT_STYLE
                    if self.expand_at_start
                    else self.TALK_BUTTON_COLLAPSED_DEFAULT_STYLE
                )
                self.update_talk_button("Talk (Hold)", styleSheet=style)
                return
            finally:
                # Clean up the temporary audio file
                logger.info("Cleaning up last audio tempfile.")
                self.clean_last_audio_tempfile()

            logger.debug(f"Transcribed text: {transcribed_text}")
            self.prompt_input.setText(transcribed_text)
            self.talk_button.setEnabled(True)
            self.on_send_button_clicked_nonblocking()

    def clean_last_audio_tempfile(self):
        """Delete the last temporary audio file if it exists."""
        if hasattr(self, "last_audio_wav_path") and self.last_audio_wav_path:
            try:
                if os.path.exists(self.last_audio_wav_path):
                    os.remove(self.last_audio_wav_path)
                    print(f"Deleted tempfile: {self.last_audio_wav_path}")
                self.last_audio_wav_path = None
            except Exception as e:
                print(f"Error deleting tempfile: {e}")

    def on_websearch_state_changed(self, state):
        """Handle websearch checkbox state change."""
        self.websearch = state == Qt.CheckState.Checked.value

    def on_autoread_state_changed(self, state):
        """Handle auto-read checkbox state change."""
        self.auto_read = state == Qt.CheckState.Checked.value

    def clear_and_exit(self):
        """Clear context and exit the application, ensuring threads are properly deleted."""
        logger.info("Application closing.")

        self.clear_context()
        # Abort the GPT worker if running
        if hasattr(self, "gpt_thread") and self.gpt_thread:
            if hasattr(self, "gpt_worker") and self.gpt_worker:
                self.gpt_worker.abort_now()
            # Wait for the thread to finish
            try:
                if self.gpt_thread.isRunning():
                    logger.info("Waiting for GPT thread to finish...")
                    self.gpt_thread.quit()
                    self.gpt_thread.wait(
                        3000
                    )  # Wait up to 3 seconds for thread to finish
            except Exception as e:
                logger.error(f"Error waiting for GPT thread to finish: {e}")

        try:
            is_playing = pygame.mixer.get_init() and pygame.mixer.music.get_busy()
            if is_playing:
                if pygame.mixer.get_init() and pygame.mixer.music.get_busy():
                    pygame.mixer.music.stop()
                    # TTS.clear()
                    logger.info("Audio playback stopped before quitting.")
        except Exception as e:
            logger.error(f"Error stopping audio playback: {e}")
        self.clean_last_audio_tempfile()

        if self.tts_service:
            self.tts_service.shutdown()

        if self.tts_thread and self.tts_thread.isRunning():
            self.tts_thread.quit()
            self.tts_thread.wait(3000)

        self.close()

    def closeEvent(self, event):
        self.clear_and_exit()
        event.accept()

    def read_system_prompt(self):
        """Read the system prompt from a file."""
        if not os.path.exists("system_prompt.txt"):
            return ""
        with open("system_prompt.txt", "r") as f:
            return f.read()

    def check_api_key(self):
        try:
            openai.chat_with_gpt5("hi")
        except requests.exceptions.HTTPError as e:
            if not self.expand_at_start:
                self.on_expand_button_toggle()

            self.update_status_bar(
                text="HTTP Error! Please check your API key or connection!",
                color="red",
                timer=-1,
            )
            self.setEnabled(False)

    ##################### STREAMING #######################
    def on_read_button_clicked_streaming(self):
        """Start playing the text - non-blocking"""
        logging.info("Read button clicked.")

        # Check if TTS worker is running
        if self.tts_service.is_playing:
            self.stop_playback()
            time.sleep(0.3)

        else:
            # Prepare the content of reply_display to be added as a chunk
            text = self.reply_display.toPlainText().strip()
            logging.debug(f"Text to read from reply_display: '{text}'")
            if text:
                logging.info("Adding chunk to TTS worker.")
                self.add_full_text(text)
            else:
                logging.error("No text in reply_display to read.")

    def on_gpt_chunk_streaming(self, chunk):
        logger.info("on_gpt_chunk_streaming called")
        if not self.first_chunk:
            style = (
                self.TALK_BUTTON_EXPANDED_INTERRUPT_STYLE
                if self.expand_at_start
                else self.TALK_BUTTON_COLLAPSED_INTERRUPT_STYLE
            )
            self.update_talk_button("Interrupt", styleSheet=style)
            self.talk_button.setEnabled(True)
            self.update_status_bar("Thinking...", "orange", -1)
            self.first_chunk = True
            QApplication.processEvents()

        t = chunk.get("type")
        if t == "response.output_text.delta":
            # Depending on provider schema, text might be in obj["delta"]["text"] or obj["output_text"]["delta"]
            delta = chunk.get("delta", {})
            if delta:
                if len(delta) < 30:
                    self.streaming_reply += delta
                    self.reply_display.setPlainText(self.streaming_reply)

                    if self.auto_read and not self.websearch:
                        self.partial_transciption += delta
                        logger.info(
                            f"Updated partial_transciption: {self.partial_transciption}"
                        )
                        if len(self.partial_transciption) > self.mininumAnswerLength:
                            logger.info(
                                "partial_transciption length exceeded mininumAnswerLength, creating chunks."
                            )
                            chunks, self.partial_transciption = (
                                self.chunker.create_chunks(self.partial_transciption)
                            )
                            logger.info(
                                f"Chunks created: {chunks}, Remaining partial_transciption: {self.partial_transciption}"
                            )
                            for chunk in chunks:
                                logger.info(f"Sending chunk to TTS: {chunk}")
                                self.add_chunk(chunk)
                else:
                    logger.info(f"Delta is long, treating as citation: {delta}")
                    if not self.citations.get(delta, 0):
                        citation_num = len(self.citations)
                        self.citations[delta] = {
                            "url": "",
                            "title": "",
                            "order": citation_num + 1,
                        }
                        logger.info(f"Added new citation: {self.citations[delta]}")

                    self.streaming_reply += f"[{self.citations[delta]['order']}]"
                    logger.info(
                        f"Appended citation order to streaming_reply: {self.streaming_reply}"
                    )

        elif t == "response.output_text.annotation.added":
            url = chunk.get("annotation", {}).get("url")
            title = chunk.get("annotation", {}).get("title", {})
            logger.info(f"Annotation added: url={url}, title={title}")
            for key in self.citations.keys():
                if url in key:
                    logger.info(f"Updating citation for key: {key}")
                    self.citations[key]["url"] = url
                    self.citations[key]["title"] = title

    def on_gpt_done_streaming(self):
        logger.info("on_gpt_done_streaming called")
        if self.gpt_worker._abort:
            logger.info("DONE AFTER ABORT")
            self.reply_display.clear()
            logger.debug("Reply display cleared due to abort.")
        else:
            logger.info("Received done")
            self.clear_status_bar()
            if self.websearch:
                logger.debug("Websearch mode active. Formatting web reply.")
                final_reply = self.format_web_reply(
                    self.streaming_reply, self.citations
                )
                self.reply_display.setPlainText(final_reply)
                if self.auto_read:
                    logger.debug(
                        "auto_read is enabled, calling on_read_button_clicked_streaming()"
                    )
                    self.on_read_button_clicked_streaming()
            else:
                if self.auto_read and self.partial_transciption:
                    logger.info(
                        f"auto_read is enabled and partial_transciption exists, adding chunk: {self.partial_transciption}"
                    )
                    self.add_chunk(self.partial_transciption)

            reply = self.streaming_reply
            logger.debug(f"Appending assistant reply to context: {reply}")
            self.context.append(
                {
                    "role": "assistant",
                    "content": [{"type": "output_text", "text": f"{reply}"}],
                }
            )
            self.first_chunk = False
            # Update the clear context button to show the number of exchanges
            self.clear_context_button.setText(f"Clear Context ({len(self.context)-1})")

            # Clear the prompt input field
            self.prompt_input.clear()
            logger.info("Prompt input cleared and context button updated.")

        logger.debug("Resetting streaming_reply, citations, and partial_transciption.")
        self.streaming_reply = ""
        self.citations = dict()
        self.partial_transciption = ""

        style = (
            self.TALK_BUTTON_EXPANDED_DEFAULT_STYLE
            if self.expand_at_start
            else self.TALK_BUTTON_COLLAPSED_DEFAULT_STYLE
        )

        logger.debug(f"Updating talk button style: {style}")
        self.update_talk_button("Talk (Hold)", styleSheet=style)
        self.talk_button.setEnabled(True)
        self.clear_status_bar()
        logger.debug("Talk button enabled.")
        self.clean_last_audio_tempfile()
        logger.debug("Cleaned last audio tempfile.")
        # Re-enable the send button when done
        self.send_button.setEnabled(True)
        self.prompt_input.setEnabled(True)
        self.prompt_input.setFocus()
        self.cleanup_gpt_thread()

    def launch_gpt_service(self):
        # Create a new worker and thread for GPT processing
        try:
            self.gpt_thread = QThread(self)
            self.gpt_worker = GPTWorker(self.context)

            # Connect signals for thread-safe communication
            self.gpt_thread.started.connect(self.gpt_worker.run)
            self.gpt_worker.chunk.connect(self.on_gpt_chunk_streaming)
            self.gpt_worker.done.connect(self.on_gpt_done_streaming)
            self.gpt_worker.error.connect(self.on_gpt_error)

            # Re-enable UI controls after thread cleanup
            self.gpt_worker.done.connect(lambda: self.read_button.setEnabled(True))
            self.gpt_worker.done.connect(lambda: self.send_button.setEnabled(True))
            self.gpt_worker.done.connect(lambda: self.prompt_input.setEnabled(True))

            self.gpt_worker.error.connect(lambda: self.read_button.setEnabled(True))
            self.gpt_worker.error.connect(lambda: self.send_button.setEnabled(True))
            self.gpt_worker.error.connect(lambda: self.prompt_input.setEnabled(True))
            return True
        except Exception as e:
            logger.error(f"Error launching GPT service: {e}")
            return False

    def cleanup_gpt_thread(self):
        logger.info("GPT thread cleanup triggered")
        if hasattr(self, "gpt_thread") and self.gpt_thread is not None:
            self.gpt_thread.quit()
            self.gpt_thread.wait()
            self.gpt_thread.deleteLater()
            self.gpt_thread = None
        if hasattr(self, "gpt_worker") and self.gpt_worker is not None:
            self.gpt_worker.deleteLater()
            self.gpt_worker = None

    def on_send_button_clicked_nonblocking(self):
        if self.tts_service.is_playing:
            logger.info("Audio playback already in progress. Stopping.")
            self.stop_playback()
            time.sleep(0.3)

        if self.prompt_input.toPlainText():
            # Disable UI controls during processing
            self.read_button.setEnabled(False)
            self.send_button.setEnabled(False)
            self.prompt_input.setEnabled(False)
            self.reply_display.clear()

            # Start the GPT service
            if not self.launch_gpt_service():
                return

            # Gather the prompt and any additional context (screenshot, clipboard)
            prompt_text = self.prompt_input.toPlainText()
            logger.info(f"Prompt text: {prompt_text!r}")
            content = [{"type": "input_text", "text": prompt_text}]

            # Add screenshot context if available
            if self.screeshot_taken:
                logger.info("Screenshot context detected.")
                if self.img_url:
                    logger.info(f"Screenshot file found: {self.img_url}")
                    # If prompt is empty, add a default question for the image
                    if not content[0]["text"]:
                        logger.info("Prompt is empty, adding default image question.")
                        content.append(
                            {"type": "input_text", "text": "What is in this image?"}
                        )
                    # Attach screenshot as context
                    content.append(openai.attach_image_message(self.img_url))
                    logger.info("Screenshot added to context.")
                    # Clean up the temporary screenshot file
                    screen_grab.cleanup_tempfile(self.img_url)
                    logger.info("Temporary screenshot file cleaned up.")
                else:
                    logger.info("No screenshot found to add to context.")
                self.screeshot_taken = False
                self.img_url = ""

            # Add clipboard context if available
            if self.clipboard_taken:
                logger.info("Clipboard context detected.")
                if self.clipboard_text:
                    logger.info(f"Clipboard text found: {self.clipboard_text!r}")
                    # If prompt is empty, add a default clipboard context message
                    if not content[0]["text"]:
                        logger.info(
                            "Prompt is empty, adding default clipboard context message."
                        )
                        content.append(
                            {
                                "type": "input_text",
                                "text": "(User forgot to add prompt. Use context from clipboard instead.",
                            }
                        )
                    # Add saved clipboard item to content
                    content.append(
                        {
                            "type": "input_text",
                            "text": f"Context from clipboard: {self.clipboard_text}",
                        }
                    )
                    logger.info("Saved clipboard text added to context.")
                else:
                    logger.info("No clipboard text found to add to context.")
                self.clipboard_taken = False
                self.clipboard_text = ""

            # Prepare the message and start the GPT worker thread
            messages = {"role": "user", "content": content}
            self.context.append(messages)
            logger.debug(f"User message: {messages}")
            logger.info("User message appended to context. Sending to OpenAI.")
            tools = [{"type": "web_search_preview"}] if self.websearch else None

            self.gpt_worker.set_content(self.context)
            self.gpt_worker.set_tools(tools)
            self.gpt_worker.moveToThread(self.gpt_thread)

            # Start the worker thread
            logger.info(
                f"Starting GPT thread with thread status: {self.gpt_thread.isRunning()}"
            )
            self.gpt_thread.start()

    ##################### STREAMING #######################

    ##################### TTS #######################

    def init_tts_service(self):
        """Initialize the persistent TTS service"""
        # Create thread for TTS service
        api_key = os.getenv("OPENAI_API_KEY")

        self.tts_thread = QThread()
        self.tts_service = TTS_S.TTSService(api_key)
        self.tts_service.moveToThread(self.tts_thread)

        # Connect signals
        self.tts_service.error_occurred.connect(self.handle_error)
        self.tts_service.playback_started.connect(self.on_playback_started)
        self.tts_service.playback_stopped.connect(self.on_playback_stopped)
        self.tts_service.playback_finished.connect(self.on_playback_finished)
        self.tts_service.chunk_generated.connect(self.start_playback)

        # Start the thread
        self.tts_thread.start()
        logger.info("TTS service initialized and started.")

    def add_chunk(self, text):
        """Add current text as a single chunk"""
        self.tts_service.add_chunk(text)
        logger.info("Chunk added to service.")

    def add_full_text(self, text):
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
        self.update_status_bar(
            text=f"TTS Error: {error_message}", color="red", timer=-1
        )

    def on_playback_finished(self):
        """Called when playback finishes naturally"""
        self.clear_status_bar()

    def on_playback_started(self):
        """Called when playback starts"""
        self.update_status_bar("Reading out loud...", "green", -1)

    def on_playback_stopped(self):
        """Called when playback is stopped"""
        self.update_status_bar("Playback Stopped", "orange", 3000)


if __name__ == "__main__":

    # Entry point for the application
    app = QApplication(sys.argv)
    window = SidekickUI()
    window.show()
    sys.exit(app.exec())
