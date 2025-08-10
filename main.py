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


class SidekickUI(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Sidekick")
        # Make the window always on top
        self.setWindowFlags(self.windowFlags() | Qt.WindowType.WindowStaysOnTopHint)
        self.init_ui()

    def init_ui(self):
        main_layout = QVBoxLayout()

        # Listen Button (hold to talk)
        listen_layout = QHBoxLayout()
        self.listen_button = QPushButton("Speak (Hold)")
        self.listen_button.setCheckable(False)
        self.listen_button.setSizePolicy(
            QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed
        )
        listen_layout.addWidget(self.listen_button)
        main_layout.addLayout(listen_layout)

        # User Prompt Input
        prompt_layout = QHBoxLayout()
        self.prompt_input = QLineEdit()
        self.prompt_input.setPlaceholderText("Type your prompt here...")
        self.send_button = QPushButton("Send")
        prompt_layout.addWidget(self.prompt_input)
        prompt_layout.addWidget(self.send_button)
        main_layout.addLayout(prompt_layout)

        # GPT Reply Display
        self.reply_display = QTextEdit()
        self.reply_display.setReadOnly(True)
        self.reply_display.setPlaceholderText("GPT reply will appear here...")
        main_layout.addWidget(self.reply_display)

        # Copy Reply Button
        copy_layout = QHBoxLayout()
        copy_layout.addSpacerItem(
            QSpacerItem(
                40, 20, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum
            )
        )
        self.copy_reply_button = QPushButton("Copy Reply")
        copy_layout.addWidget(self.copy_reply_button)
        main_layout.addLayout(copy_layout)

        # Screen Content Controls
        screen_layout = QHBoxLayout()
        self.screen_radio = QRadioButton("Automatically grab screen content")
        screen_layout.addWidget(self.screen_radio)
        screen_layout.addSpacerItem(
            QSpacerItem(
                40, 20, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum
            )
        )
        main_layout.addLayout(screen_layout)

        exit_layout = QHBoxLayout()
        # Add "Grab screen content" button here
        self.listen_grab_screen_button = QPushButton("Grab Screen Content")
        exit_layout.addWidget(self.listen_grab_screen_button)
        exit_layout.addSpacerItem(
            QSpacerItem(
                40, 20, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum
            )
        )
        # Exit Button
        exit_layout.addSpacerItem(
            QSpacerItem(
                40, 20, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum
            )
        )

        self.exit_button = QPushButton("Exit App")
        exit_layout.addWidget(self.listen_grab_screen_button)

        exit_layout.addWidget(self.exit_button)

        main_layout.addLayout(exit_layout)

        self.setLayout(main_layout)
        self.setMinimumWidth(400)


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = SidekickUI()
    window.show()
    sys.exit(app.exec())
