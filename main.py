import sys
import datetime
from venv import logger
import re
from PyQt6.QtCore import QObject, pyqtSignal, pyqtSlot

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
import TTS
import asyncio
import openai
import os
import json
import pygame, requests

import sounddevice as sd
import numpy as np
import threading
import tempfile
import wave
import logging
from TTS import enqueue as tts_enqueue, clear as tts_clear


class GPTWorker(QObject):
    chunk = pyqtSignal(dict)  # stream text deltas
    done = pyqtSignal()  # finished successfully
    error = pyqtSignal(str)  # error message
    abort = pyqtSignal(bool)

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
                    self.abort.emit(True)
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
                    TTS.clear()
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

        # Set dark mode app-wide style to match button_dark_style, with more padding and smaller font

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

        # Initialize SidekickUI state variables
        self.clipboard = False
        self.screeshot = False
        self.websearch = False
        self.auto_read = True
        self.screeshot_taken = False
        self.clipboard_taken = False
        self.img_url = ""
        self.clipboard_text = ""
        self.right_widget_width = 140
        self.expand_at_start = True
        self.talk_button_height_after_expand = 35
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
        # Create worker + thread
        self.gpt_thread = None
        self.gpt_worker = None

        self.streaming_reply = ""
        self.citations = dict()
        self.partial_transciption = ""

        self.init_ui()

    def init_ui(self):
        """Set up the UI layout and widgets."""
        # Set minimum app width
        main_layout = QVBoxLayout()

        # --- Top Row: Talk and Expand Buttons ---
        talk_layout = QHBoxLayout()

        # Talk button for voice input
        self.talk_button = QPushButton("Talk (Hold)")
        self.talk_button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.talk_button.pressed.connect(self.on_talk_button_pressed)
        self.talk_button.released.connect(self.on_talk_button_released)

        # Expand/collapse button
        self.expand_button = QPushButton()
        self.expand_button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.expand_button.clicked.connect(self.on_expand_button_toggle)

        # Set initial expand/collapse state
        if self.expand_at_start:
            # Style for talk button
            self.talk_button.setStyleSheet(self.TALK_BUTTON_EXPANDED_DEFAULT_STYLE)

            # Style for expand button
            self.expand_button.setStyleSheet(self.EXPAND_BUTTON_EXPANDED_DEFAULT_STYLE)
            self.expand_button.setFixedWidth(40)
            self.expand_button.setText("-")
            self.resize(700, 500)

        else:
            # Style for talk button
            self.talk_button.setStyleSheet(self.EXPAND_BUTTON_COLLAPSED_DEFAULT_STYLE)

            # Style for expand button
            self.expand_button.setStyleSheet(self.EXPAND_BUTTON_COLLAPSED_DEFAULT_STYLE)
            self.expand_button.setText("+")
            self.talk_button.setFixedSize(100, 60)
            self.expand_button.setFixedWidth(40)
            self.expand_button.setFixedHeight(self.talk_button.height())
            target_width = 200
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
        self.prompt_input.setPlaceholderText("Type your prompt [Enter to send]...")
        # Style is now set app-wide

        # Install event filter for Enter key
        self.prompt_input_event_filter = PromptInputEventFilter(self)
        self.prompt_input.installEventFilter(self.prompt_input_event_filter)

        # Right: Send button
        right_layout = QVBoxLayout()
        self.screenshot_button = QPushButton("+ Screenshot")
        self.screenshot_button.clicked.connect(self.on_screenshot_button_clicked)
        self.clipboard_button = QPushButton("+ Clipboard")
        self.clipboard_button.clicked.connect(self.on_clipboard_button_clicked)
        self.send_button = QPushButton("Send")
        self.send_button.clicked.connect(self.on_send_button_clicked_nonblocking)
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
        self.checkbox_websearch.stateChanged.connect(self.on_websearch_state_changed)

        # Auto-read reply checkbox
        self.checkbox_autoread = QCheckBox("Auto-Read")
        self.checkbox_autoread.setChecked(self.auto_read)
        self.checkbox_autoread.stateChanged.connect(self.on_autoread_state_changed)

        # Copy reply button
        self.copy_reply_button = QPushButton("Copy")
        self.copy_reply_button.clicked.connect(self.on_copy_reply_button_clicked)

        # Read/Stop TTS button
        self.read_button = QPushButton("Read/Stop")
        self.read_button.clicked.connect(self.on_read_button_clicked)

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
        context_options_layout.addWidget(self.load_conversation_button)

        # Save conversation button
        self.save_conversation_button = QPushButton("Save")
        self.save_conversation_button.clicked.connect(self.save_conversation)
        context_options_layout.addWidget(self.save_conversation_button)

        # Clear context button
        self.clear_context_button = QPushButton(
            f"Clear Context ({len(self.context)-1})"
        )
        self.clear_context_button.clicked.connect(self.clear_context)

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

    # This method handles sending a prompt to GPT in a non-blocking way using a worker thread.
    # If a previous thread is running, it aborts it. Otherwise, it prepares the context and starts a new thread.
    def on_send_button_clicked_nonblocking(self):

        if self.gpt_thread:
            if self.gpt_thread.isRunning():
                # Abort the currently running GPT worker if present
                self.gpt_worker.abort_now()
                style = (
                    self.TALK_BUTTON_EXPANDED_DEFAULT_STYLE
                    if self.expand_at_start
                    else self.TALK_BUTTON_COLLAPSED_DEFAULT_STYLE
                )
                self.update_talk_button("Talk (Hold)", styleSheet=style)
        else:

            style = (
                self.TALK_BUTTON_EXPANDED_INTERRUPT_STYLE
                if self.expand_at_start
                else self.TALK_BUTTON_COLLAPSED_INTERRUPT_STYLE
            )
            self.update_talk_button("Interrupt", styleSheet=style)
            self.update_status_bar("Thinking...", "orange", -1)
            # Create a new worker and thread for GPT processing
            self.gpt_thread = QThread(self)
            self.gpt_worker = GPTWorker(self.context)

            # Connect signals for thread-safe communication
            self.gpt_thread.started.connect(self.gpt_worker.run)
            self.gpt_worker.chunk.connect(self.on_gpt_chunk)
            self.gpt_worker.done.connect(self.on_gpt_done)
            self.gpt_worker.error.connect(self.on_gpt_error)
            self.gpt_worker.abort.connect(self.on_gpt_abort)

            # Ensure proper cleanup after completion, abort, or error
            for signal in [
                self.gpt_worker.done,
                self.gpt_worker.abort,
                self.gpt_worker.error,
            ]:
                signal.connect(self.gpt_thread.quit)
                signal.connect(self.gpt_worker.deleteLater)
            self.gpt_thread.finished.connect(self.gpt_thread.deleteLater)
            self.gpt_thread.finished.connect(lambda: setattr(self, "gpt_thread", None))
            self.gpt_thread.finished.connect(lambda: setattr(self, "gpt_worker", None))

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
            self.gpt_thread.start()

    def on_gpt_chunk(self, chunk):
        logger.info(f"Received chunk")
        t = chunk.get("type")
        if t == "response.output_text.delta":
            # Depending on provider schema, text might be in obj["delta"]["text"] or obj["output_text"]["delta"]
            delta = chunk.get("delta", {})
            if delta:
                if len(delta) < 30:
                    self.streaming_reply += delta
                    self.reply_display.setPlainText(self.streaming_reply)
                    QApplication.processEvents()
                    if self.auto_read and not self.websearch:
                        self.partial_transciption += delta
                        if (
                            self.partial_transciption[-1] in [".", "!", "?", "\n"]
                            and len(self.partial_transciption) > 20
                        ):
                            last_few = self.streaming_reply[-10:]
                            match = re.search(r"(?<!\d)([.!?])(?!\d)(?:\s|$)", last_few)
                            if match:
                                tts_enqueue(self.partial_transciption)
                                self.partial_transciption = ""
                else:
                    if not self.citations.get(delta, 0):
                        citation_num = len(self.citations)
                        self.citations[delta] = {
                            "url": "",
                            "title": "",
                            "order": citation_num + 1,
                        }

                    self.streaming_reply += f"[{self.citations[delta]['order']}]"

        elif t == "response.output_text.annotation.added":
            url = chunk.get("annotation", {}).get("url")
            title = chunk.get("annotation", {}).get("title", {})
            for key in self.citations.keys():
                if url in key:
                    self.citations[key]["url"] = url
                    self.citations[key]["title"] = title

        elif t == "response.output_text.done":
            if self.websearch:
                final_reply = self.format_web_reply(
                    self.streaming_reply, self.citations
                )
                self.reply_display.setPlainText(final_reply)
                QApplication.processEvents()

                asyncio.run(TTS.speak_async(self.streaming_reply))
                return final_reply
            else:
                tts_enqueue(self.partial_transciption)
                return self.streaming_reply

    def process_gpt_stream(self, content, tools=None):
        streaming_reply = ""
        citations = dict()
        partial_transciption = ""

        for obj in openai.chat_with_gpt5_stream(messages=content, tools=tools):
            t = obj.get("type")
            if t == "response.output_text.delta":
                # Depending on provider schema, text might be in obj["delta"]["text"] or obj["output_text"]["delta"]
                delta = obj.get("delta", {})
                if delta:
                    if len(delta) < 30:
                        streaming_reply += delta
                        self.reply_display.setPlainText(streaming_reply)
                        QApplication.processEvents()
                        if self.auto_read and not self.websearch:
                            partial_transciption += delta
                            if (
                                partial_transciption[-1] in [".", "!", "?", "\n"]
                                and len(partial_transciption) > 20
                            ):
                                last_few = streaming_reply[-10:]
                                match = re.search(
                                    r"(?<!\d)([.!?])(?!\d)(?:\s|$)", last_few
                                )
                                if match:
                                    tts_enqueue(partial_transciption)
                                    partial_transciption = ""
                    else:
                        if not citations.get(delta, 0):
                            citation_num = len(citations)
                            citations[delta] = {
                                "url": "",
                                "title": "",
                                "order": citation_num + 1,
                            }

                        streaming_reply += f"[{citations[delta]['order']}]"

            elif t == "response.output_text.annotation.added":
                url = obj.get("annotation", {}).get("url")
                title = obj.get("annotation", {}).get("title", {})
                for key in citations.keys():
                    if url in key:
                        citations[key]["url"] = url
                        citations[key]["title"] = title

            elif t == "response.output_text.done":
                if self.websearch:
                    final_reply = self.format_web_reply(streaming_reply, citations)
                    self.reply_display.setPlainText(final_reply)
                    QApplication.processEvents()

                    asyncio.run(TTS.speak_async(streaming_reply))
                    return final_reply
                else:
                    tts_enqueue(partial_transciption)
                    return streaming_reply

    def on_gpt_done(self):
        logger.info(f"Received done")
        if self.websearch:
            final_reply = self.format_web_reply(self.streaming_reply, self.citations)
            self.reply_display.setPlainText(final_reply)
            QApplication.processEvents()
            asyncio.run(TTS.speak_async(self.streaming_reply))
            return final_reply
        else:
            tts_enqueue(self.partial_transciption)

        reply = self.streaming_reply
        self.context.append(
            {
                "role": "assistant",
                "content": [{"type": "output_text", "text": f"{reply}"}],
            }
        )

        self.clear_status_bar()
        # Update the clear context button to show the number of exchanges
        self.clear_context_button.setText(f"Clear Context ({len(self.context)-1})")
        # Clear the prompt input field
        self.prompt_input.clear()
        logger.info("Prompt input cleared and context button updated.")

        self.prompt_input.clear()
        self.streaming_reply = ""
        self.citations = dict()
        self.partial_transciption = ""

        style = (
            self.TALK_BUTTON_EXPANDED_DEFAULT_STYLE
            if self.expand_at_start
            else self.TALK_BUTTON_COLLAPSED_DEFAULT_STYLE
        )
        self.update_talk_button("Talk (Hold)", styleSheet=style)
        self.clean_last_audio_tempfile()
        self.clear_status_bar()

    def on_gpt_error(self, error):
        logger.error(f"Received error: {error}")
        self.update_status_bar(f"Error occured. Please check log.", "red", 3000)
        self.reply_display.clear()
        self.prompt_input.clear()
        self.streaming_reply = ""
        self.citations = dict()
        self.partial_transciption = ""
        self.clean_last_audio_tempfile()
        style = (
            self.TALK_BUTTON_EXPANDED_DEFAULT_STYLE
            if self.expand_at_start
            else self.TALK_BUTTON_COLLAPSED_DEFAULT_STYLE
        )
        self.update_talk_button("Talk (Hold)", styleSheet=style)

    def on_gpt_abort(self, abort):
        logger.info(f"Received abort: {abort}")
        self.update_status_bar("Aborting previous prompt...", "red", 3000)
        self.reply_display.clear()
        self.prompt_input.clear()
        self.streaming_reply = ""
        self.citations = dict()
        self.partial_transciption = ""
        self.clean_last_audio_tempfile()
        style = (
            self.TALK_BUTTON_EXPANDED_DEFAULT_STYLE
            if self.expand_at_start
            else self.TALK_BUTTON_COLLAPSED_DEFAULT_STYLE
        )
        self.update_talk_button("Talk (Hold)", styleSheet=style)

    # def on_send_button_clicked(self):
    #     """
    #     Handle the Send button click event.

    #     This method collects the user prompt and any additional context (such as screenshot or clipboard),
    #     prepares the message for OpenAI, sends it, and updates the UI accordingly.
    #     """
    #     logger.info("Send button clicked.")
    #     self.update_status_bar(
    #         text="Prompt sent! Waiting for GPT response...",
    #         color="green",
    #         timer=-1,
    #     )
    #     # Set the talk button style to indicate "thinking" state
    #     if self.expand_at_start:
    #         self.update_talk_button(
    #             "Thinking...",
    #             style="""
    #             QPushButton {
    #                 border-radius: 10px;
    #                 color: white;
    #                 background-color:  #27ae60;
    #                 padding: 6px 14px;
    #                 font-size: 13px;
    #             }
    #             QPushButton:hover {
    #                 background-color:  #27ae60;
    #             }
    #             QPushButton:pressed {
    #                 background-color: #27ae60;
    #             }
    #             """,
    #         )
    #     else:
    #         self.update_talk_button(
    #             "Thinking...",
    #             style="""
    #             QPushButton {
    #                 border-radius: 20px;
    #                 color: white;
    #                 background-color:  #27ae60;
    #                 padding: 6px 14px;
    #                 font-size: 13px;
    #             }
    #             QPushButton:hover {
    #                 background-color:  #27ae60;
    #             }
    #             QPushButton:pressed {
    #                 background-color: #27ae60;
    #             }
    #             """,
    #         )

    #     logger.info("Preparing to send prompt to OpenAI.")

    #     # Get the prompt text from the input field
    #     prompt_text = self.prompt_input.toPlainText()
    #     logger.info(f"Prompt text: {prompt_text!r}")
    #     content = [{"type": "input_text", "text": prompt_text}]

    #     # Handle screenshot context if present
    #     if self.screeshot_taken:
    #         logger.info("Screenshot context detected.")
    #         if self.img_url:
    #             logger.info(f"Screenshot file found: {self.img_url}")
    #             # If prompt is empty, add a default question for the image
    #             if not content[0]["text"]:
    #                 logger.info("Prompt is empty, adding default image question.")
    #                 content.append(
    #                     {"type": "input_text", "text": "What is in this image?"}
    #                 )
    #             # Attach screenshot as context
    #             content.append(openai.attach_image_message(self.img_url))
    #             logger.info("Screenshot added to context.")
    #             # Clean up the temporary screenshot file
    #             screen_grab.cleanup_tempfile(self.img_url)
    #             logger.info("Temporary screenshot file cleaned up.")
    #         else:
    #             logger.info("No screenshot found to add to context.")
    #         self.screeshot_taken = False
    #         self.img_url = ""

    #     # Handle clipboard context if present
    #     if self.clipboard_taken:
    #         logger.info("Clipboard context detected.")
    #         if self.clipboard_text:
    #             logger.info(f"Clipboard text found: {self.clipboard_text!r}")
    #             # If prompt is empty, add a default clipboard context message
    #             if not content[0]["text"]:
    #                 logger.info(
    #                     "Prompt is empty, adding default clipboard context message."
    #                 )
    #                 content.append(
    #                     {
    #                         "type": "input_text",
    #                         "text": "(User forgot to add prompt. Use context from clipboard instead.",
    #                     }
    #                 )
    #             # Add saved clipboard item to content
    #             content.append(
    #                 {
    #                     "type": "input_text",
    #                     "text": f"Context from clipboard: {self.clipboard_text}",
    #                 }
    #             )
    #             logger.info("Saved clipboard text added to context.")
    #         else:
    #             logger.info("No clipboard text found to add to context.")
    #         self.clipboard_taken = False
    #         self.clipboard_text = ""

    #     # Prepare and send message to OpenAI
    #     messages = {"role": "user", "content": content}
    #     self.context.append(messages)
    #     logger.debug(f"User message: {messages}")
    #     logger.info("User message appended to context. Sending to OpenAI.")

    #     try:
    #         # If websearch is enabled, add the web_search_preview tool
    #         tools = [{"type": "web_search_preview"}] if self.websearch else None
    #         logger.info(f"Calling process_gpt_stream with tools: {tools}")
    #         reply = self.process_gpt_stream(content=self.context, tools=tools)

    #     except Exception as e:
    #         logger.error(f"Couldn't send message to OpenAI: {e}")

    #     # Append assistant's reply to the context
    #     self.context.append(
    #         {
    #             "role": "assistant",
    #             "content": [{"type": "output_text", "text": f"{reply}"}],
    #         }
    #     )

    #     self.clear_status_bar()
    #     # Update the clear context button to show the number of exchanges
    #     self.clear_context_button.setText(f"Clear Context ({len(self.context)-1})")
    #     # Clear the prompt input field
    #     self.prompt_input.clear()
    #     logger.info("Prompt input cleared and context button updated.")

    #     # Reset the talk button style to ready state
    #     if self.expand_at_start:
    #         self.update_talk_button(
    #             "Talk (Hold)",
    #             style="""
    #             QPushButton {
    #                 border-radius: 10px;
    #                 color: white;
    #                 background-color: #3498db;
    #                 padding: 6px 14px;
    #                 font-size: 13px;
    #             }
    #             QPushButton:hover {
    #                 background-color: #2980b9;
    #             }
    #             QPushButton:pressed {
    #                 background-color: #e74c3c; /* Record button red on press */
    #                 color: white; /* White text for contrast */
    #             }
    #             """,
    #         )
    #     else:
    #         self.update_talk_button(
    #             "Talk (Hold)",
    #             styleSheet="""
    #             QPushButton {
    #                 border-radius: 10px;
    #                 color: white;
    #                 background-color: #3498db;
    #                 padding: 6px 14px;
    #                 font-size: 13px;
    #             }
    #             QPushButton:hover {
    #                 background-color: #2980b9;
    #             }
    #             QPushButton:pressed {
    #                 background-color: #e74c3c; /* Record button red on press */
    #                 color: white; /* White text for contrast */
    #             }
    #             """,
    #         )

    #     logger.info("UI reset to ready state after sending prompt.")

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

    def on_read_button_clicked(self):
        """Read the reply text aloud or stop playback."""
        # Check if audio is currently playing using pygame.mixer
        try:
            is_playing = pygame.mixer.get_init() and pygame.mixer.music.get_busy()
            print(f"Audio playing: {is_playing}")
        except Exception as e:
            print(f"Error checking audio playback: {e}")
            self.update_status_bar(
                text="Error checking audio playback",
                color="red",
                timer=-1,
            )
            return

        if not is_playing:
            # Read the reply text aloud using TTS
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
                if widget is not self.talk_button and widget is not self.expand_button:
                    widget.hide()

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

            target_width = 200
            target_height = 100
            self.setMinimumSize(200, 100)
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
            # Style for talk button
            self.talk_button.setStyleSheet(self.TALK_BUTTON_EXPANDED_DEFAULT_STYLE)

            # Style for expand button
            self.expand_button.setStyleSheet(self.EXPAND_BUTTON_EXPANDED_DEFAULT_STYLE)
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

            self.setMaximumSize(700, 500)

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
            self.activateWindow()  # Ensure pending events are processed post-animation
            (
                QTimer.singleShot(10, self.prompt_input.setFocus)
                if self.expand_at_start
                else QTimer.singleShot(10, self.talk_button.setFocus)
            )
            (
                QTimer.singleShot(0, lambda: self.setFixedSize(700, 500))
                if self.expand_at_start
                else QTimer.singleShot(0, lambda: self.setFixedSize(200, 100))
            )

        self.anim_group.finished.connect(_on_anims_finished)
        self.anim_group.start()

    def set_app_start_mode(self):
        """Show or hide widgets based on the initial expand/collapse state."""
        if self.expand_at_start:
            for widget in self.findChildren(QWidget):
                widget.show()
        else:
            for widget in self.findChildren(QWidget):
                if widget not in [
                    self.talk_button,
                    self.expand_button,
                ]:
                    widget.hide()

    def on_talk_button_pressed(self):

        if self.gpt_thread:
            if self.gpt_thread.isRunning():
                return
        else:
            """Start recording audio for voice input."""
            tts_clear()
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
                # Abort the currently running GPT worker if present
                self.gpt_worker.abort_now()
                style = (
                    self.TALK_BUTTON_EXPANDED_DEFAULT_STYLE
                    if self.expand_at_start
                    else self.TALK_BUTTON_COLLAPSED_DEFAULT_STYLE
                )
                self.update_talk_button("Talk (Hold)", styleSheet=style)
        else:
            self.clear_status_bar()
            """Stop recording, transcribe audio, and send as prompt."""
            logger.debug("Talk button released")
            logger.debug("Thinking...")
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
                with tempfile.NamedTemporaryFile(
                    suffix=".wav", delete=False
                ) as wav_temp:
                    with wave.open(wav_temp, "wb") as wf:
                        wf.setnchannels(1)
                        wf.setsampwidth(2)  # 16-bit audio
                        wf.setframerate(self.audio_fs)
                        wf.writeframes(audio_data.tobytes())
                    self.last_audio_wav_path = wav_temp.name  # Store path for later use

                logger.debug(
                    f"Audio saved as wav in tempfile: {self.last_audio_wav_path}"
                )
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

    def clear_status_bar(self):
        """Reset the status bar to 'Ready'."""
        self.status_bar.setText("Ready")
        self.status_bar.setStyleSheet("color: grey;")

    def on_websearch_state_changed(self, state):
        """Handle websearch checkbox state change."""
        self.websearch = state == Qt.CheckState.Checked.value

    def on_autoread_state_changed(self, state):
        """Handle auto-read checkbox state change."""
        self.auto_read = state == Qt.CheckState.Checked.value

    def clear_and_exit(self):
        """Clear context and exit the application."""
        self.clear_context()
        self.close()

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


if __name__ == "__main__":

    # Set up logger
    import logging_config

    logging_config.setup_root_logging("sidekick.log")
    logger = logging.getLogger(__name__)

    # Entry point for the application
    app = QApplication(sys.argv)
    window = SidekickUI()
    window.show()
    sys.exit(app.exec())
