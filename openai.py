import os
import requests

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_API_BASE = "https://api.openai.com/v1"


def openai_headers():
    return {
        "Authorization": f"Bearer {OPENAI_API_KEY}",
        "Content-Type": "application/json",
    }


def chat_with_gpt5(
    messages,
    model="gpt-5-mini",  # May need to be "gpt-5-2025-08-07" or similar
    tools=None,
    tool_choice=None,
    max_tokens=800,
    # New GPT-5 parameters
    verbosity=None,  # Controls response length/detail
    reasoning_effort=None,  # "low", "medium", "high" for thinking depth
    stream=False,
):
    """
    Updated for GPT-5 API with new parameters
    """
    url = f"{OPENAI_API_BASE}/responses"
    payload = {
        "model": model,
        "input": messages,
        "max_output_tokens": max_tokens,
        "stream": stream,
    }

    # Add GPT-5 specific parameters if provided
    if verbosity is not None:
        payload["verbosity"] = verbosity
    if reasoning_effort is not None:
        payload["reasoning_effort"] = reasoning_effort

    # Existing parameters
    if tools:
        payload["tools"] = tools
    if tool_choice:
        payload["tool_choice"] = tool_choice
    response = requests.post(url, headers=openai_headers(), json=payload)

    if response.status_code == 400:
        error_data = response.json()
        print(f"\n=== ERROR DETAILS ===")
        print(f"Error Type: {error_data.get('error', {}).get('type', 'Unknown')}")
        print(
            f"Error Message: {error_data.get('error', {}).get('message', 'No message')}"
        )
        print(f"Error Code: {error_data.get('error', {}).get('code', 'No code')}")
        print(f"Error Param: {error_data.get('error', {}).get('param', 'No param')}")

    response.raise_for_status()
    assistant_text = ""
    for block in response.json().get("output", []):
        if block.get("role") == "assistant":
            for content in block.get("content", []):
                if content.get("type") == "output_text":
                    assistant_text += content.get("text", "")
    return assistant_text


def attach_image_message(image_path):
    """
    Returns a message dict for OpenAI API with an attached image.
    image_path: path to the image file
    prompt_text: optional, text to send with the image
    """
    try:
        with open(image_path, "rb") as f:
            image_data = f.read()
    except FileNotFoundError:
        print(f"Image file not found: {image_path}")
        return {
            "type": "input_text",
            "text": "I didn't include an image. Ask me to attach it correctly.",
        }

    import base64
    import mimetypes

    def get_image_mime_type(image_path):
        mime_type, _ = mimetypes.guess_type(image_path)
        return mime_type or "image/png"  # fallback

    mime_type = get_image_mime_type(image_path)

    b64_image = base64.b64encode(image_data).decode("utf-8")

    return {
        "type": "input_image",
        "image_url": f"data:{mime_type};base64,{b64_image}",
    }


def transcribe_audio(
    audio_path, model="whisper-1", language=None, prompt=None, response_format="text"
):
    """
    Uses OpenAI's speech-to-text (Whisper) API to transcribe audio.
    audio_path: path to audio file (wav, mp3, m4a, etc.)
    model: "whisper-1" (as of 2024-06)
    language: optional, e.g. "en"
    prompt: optional, text prompt to guide transcription
    response_format: "text", "json", "srt", "verbose_json", etc.
    """
    url = f"{OPENAI_API_BASE}/audio/transcriptions"
    headers = {"Authorization": f"Bearer {OPENAI_API_KEY}"}
    files = {
        "file": (os.path.basename(audio_path), open(audio_path, "rb")),
        "model": (None, model),
        "response_format": (None, response_format),
    }
    if language:
        files["language"] = (None, language)
    if prompt:
        files["prompt"] = (None, prompt)
    response = requests.post(url, headers=headers, files=files)
    response.raise_for_status()
    if response_format == "json" or response_format == "verbose_json":
        return response.json()
    return response.text


if __name__ == "__main__":
    # Example usage:
    messages = [{"role": "user", "content": [{"type": "input_text", "text": "Hello"}]}]
    reply = chat_with_gpt5(messages)

    # To send an image:
    # img_msg = attach_image_message("my_image.png", "What is in this image?")
    # messages = [img_msg]
    # reply = chat_with_gpt5(messages, model="gpt-4o")
    # print(reply["choices"][0]["message"]["content"])

    # To transcribe audio:
    # transcript = transcribe_audio("audio_sample.wav")
    # print(transcript)
