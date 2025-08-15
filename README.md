# Sidekick

A floating, always-on-top mini-app for seamless OpenAI GPT interaction via voice, text, and screen context, built with PyQt6.

> **Note:** Sidekick is currently developed and tested for **macOS**. Some features (such as screenshot and clipboard integration) use macOS-specific APIs.

## Overview

Sidekick is a compact desktop application built with PyQt6, designed to stay above all other windows for instant access to OpenAI's GPT models. You can interact using your voice (hold-to-talk), type prompts, or add context from your clipboard or a screenshot. Sidekick is optimized for quick, context-rich AI assistance with minimal distraction.

## Features

- **Always-on-top window** – Remains visible above all other apps (macOS only)
- **Voice input (hold-to-talk)** – Hold the "Talk" button to record and transcribe your prompt
- **Text input** – Type prompts directly into the interface
- **Clipboard and screenshot context** – Instantly add clipboard text or capture a screenshot as context for your prompt (macOS only)
- **OpenAI GPT integration** – Sends your prompt and context to GPT and displays the reply
- **Copy and Read Aloud** – Copy GPT's reply or have it read aloud with TTS
- **Animated expand/collapse UI** – Switch between compact and expanded modes with smooth animations
- **Conversation history** – Save/load your conversation for later reference
- **Minimal, responsive design** – Lightweight and non-intrusive, optimized for fast workflow

## Installation

### Prerequisites

- macOS 12.0 or higher
- Python 3.8 or higher
- OpenAI API key
- Microphone access (for voice input)
- Screen recording permissions (for context capture)
- [PyQt6](https://pypi.org/project/PyQt6/)

### Setup

1. Clone the repository:

   ```bash
   git clone https://github.com/Nicholas-Mitri/SideKick
   cd sidekick
   ```

2. (Optional) Create and activate a virtual environment:

   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   ```

3. Install the required dependencies:

   ```bash
   pip install -r requirements.txt
   ```

4. Set your OpenAI API key as an environment variable:

   ```bash
   export OPENAI_API_KEY=your-api-key-here
   ```

5. Run the application:

   ```bash
   python main.py
   ```

> **Note:** Sidekick is not tested or supported on Windows or Linux at this time. Some features may not work outside of macOS.

## Quick Start Guide

1. **Launch Sidekick**
   Open a terminal in the `sidekick` directory and run:

   ```bash
   python main.py
   ```

2. **Start a Conversation**

   - Type your question or prompt in the input box and press **Enter**.
   - Or, click the **Talk** button and speak your question (microphone required).

3. **Use Voice Features**

   - Press and hold the **Talk** button to start voice input.
   - Wait for the "Listening..." status, then speak.
   - Let go of the **Talk** button to stop recording and send your prompt.
   - Sidekick will transcribe and respond using GPT.

4. **Save or Load Conversations**

   - Click the **Save** button to save your current conversation.
   - Click the **Load** button to restore a previous conversation.

5. **Clipboard & Screenshot**

   - Use the clipboard or screenshot buttons to quickly send copied text or a screenshot to Sidekick for context or questions.

6. **Expand/Collapse the App**

   - Use the expand/collapse button to switch between compact and expanded views.

7. **Interrupt a Response**

   - While Sidekick is generating a response, the **Talk** button turns orange and displays "Interrupt".
   - Click the orange **Interrupt** button to abort the current prompt and stop the response immediately.

8. **Stop or Replay Audio Response**
   - If Sidekick is reading a response aloud, click the **Read/Stop** button to immediately stop audio playback.
   - To hear the last response again, click the **Read/Stop** button (if available).

> For best results, ensure your OpenAI API key is set and you have granted microphone and screen recording permissions.
