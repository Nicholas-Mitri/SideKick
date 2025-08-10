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
        self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint)
        self.init_ui()

    def init_ui(self):
        main_layout = QVBoxLayout()

        # GPT Reply Display
        self.reply_display = QTextEdit()
        self.reply_display.setReadOnly(True)
        self.reply_display.setPlaceholderText("GPT reply will appear here...")
        main_layout.addWidget(QLabel("GPT Reply:"))
        main_layout.addWidget(self.reply_display)

        # User Prompt Input
        prompt_layout = QHBoxLayout()
        self.prompt_input = QLineEdit()
        self.prompt_input.setPlaceholderText("Type your prompt here...")
        self.send_button = QPushButton("Send")
        prompt_layout.addWidget(self.prompt_input)
        prompt_layout.addWidget(self.send_button)
        main_layout.addLayout(prompt_layout)

        # Listen Button (hold to talk)
        listen_layout = QHBoxLayout()
        self.listen_button = QPushButton("🎤 Hold to Listen")
        self.listen_button.setCheckable(False)
        listen_layout.addWidget(self.listen_button)
        listen_layout.addSpacerItem(
            QSpacerItem(
                40, 20, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum
            )
        )
        main_layout.addLayout(listen_layout)

        # Screen Content Radio Button
        screen_layout = QHBoxLayout()
        self.screen_radio = QRadioButton("Include screen content as context")
        screen_layout.addWidget(self.screen_radio)
        screen_layout.addSpacerItem(
            QSpacerItem(
                40, 20, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum
            )
        )
        main_layout.addLayout(screen_layout)

        # Exit Button
        exit_layout = QHBoxLayout()
        self.exit_button = QPushButton("Exit App")
        exit_layout.addSpacerItem(
            QSpacerItem(
                40, 20, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum
            )
        )
        exit_layout.addWidget(self.exit_button)
        main_layout.addLayout(exit_layout)

        self.setLayout(main_layout)
        self.setMinimumWidth(400)


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = SidekickUI()
    window.show()
    sys.exit(app.exec())
