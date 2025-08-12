# Sidekick

A floating, always-on-top mini-app for seamless OpenAI GPT interaction via voice, text, and screen context, built with PyQt6.

## Overview

Sidekick is a compact desktop application built with PyQt6 that stays above all other windows for instant access to OpenAI's GPT models. You can interact using your voice (hold-to-talk), type prompts, or add context from your clipboard or a screenshot. Sidekick is designed for quick, context-rich AI assistance with minimal distraction.

## Features

- **Always-on-top window** – Stays visible above all other apps for quick access
- **Voice input (hold-to-talk)** – Hold the "Talk" button to record and transcribe your prompt
- **Text input** – Type prompts directly into the interface
- **Clipboard and screenshot context** – Instantly add clipboard text or capture a screenshot as context for your prompt
- **OpenAI GPT integration** – Sends your prompt and context to GPT and displays the reply
- **Copy and Read Aloud** – Copy GPT's reply or have it read aloud with TTS
- **Animated expand/collapse UI** – Switch between compact and expanded modes with smooth animations
- **Conversation history** – Save/load your conversation for later reference
- **Minimal, responsive design** – Lightweight and non-intrusive, optimized for fast workflow

## Installation

### Prerequisites

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

2. (Optional but recommended) Create and activate a virtual environment:

   ```bash
   python -m venv .venv
   source .venv/bin/activate  # On Windows use: .venv\Scripts\activate
   ```

3. Install the required dependencies:

   ```bash
   pip install -r requirements.txt
   ```

4. Set your OpenAI API key as an environment variable:

   ```bash
   export OPENAI_API_KEY=your-api-key-here  # On Windows use: set OPENAI_API_KEY=your-api-key-here
   ```

5. Run the application:

   ```bash
   python main.py
   ```
