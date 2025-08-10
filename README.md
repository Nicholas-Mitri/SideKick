# Sidekick

An always-on-top mini application that provides seamless interaction with OpenAI GPT through voice prompts and screen context, built with PyQt6.

## Overview

Sidekick is a lightweight desktop application built on PyQt6, designed to stay on top of your other windows for quick access to OpenAI's GPT capabilities. It supports both voice and text prompts, and can capture screen content as context, making AI assistance just a click or voice command away.

## Features

- **Always-on-top Qt window** - Remains visible above other applications
- **Voice input** - Speak your prompts using your microphone
- **Text input** - Type prompts directly in the interface
- **Screen capture integration** - Seamlessly grab screen content for context
- **OpenAI GPT integration** - Direct access to GPT models via API
- **Minimal footprint** - Lightweight, responsive, and non-intrusive
- **Quick access** - Global hotkey support for instant activation

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
   git clone https://github.com/yourusername/sidekick.git
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
