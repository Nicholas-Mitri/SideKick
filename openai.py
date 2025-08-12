import os
import requests
import json
from PyQt6.QtWidgets import QApplication
import asyncio, TTS, re
from TTS import enqueue as tts_enqueue, clear as tts_clear

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
    reasoning=None,  # {"effort": "medium"}
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


def chat_with_gpt5_stream(
    messages,
    model="gpt-5-mini",  # May need to be "gpt-5-2025-08-07" or similar
    tools=[{"type": "web_search_preview"}],
    # New GPT-5 parameters
    reasoning=None,  # {"effort": "medium"},
    UI_object=None,
):
    """
    Updated for GPT-5 API with new parameters
    """
    url = f"{OPENAI_API_BASE}/responses"
    payload = {
        "model": model,
        "input": messages,
        "stream": True,
    }

    # Existing parameters
    if tools and UI_object.websearch:
        payload["tools"] = tools

    streaming_reply = ""
    partial_transciption = ""
    citations = dict()

    with requests.post(url, headers=openai_headers(), json=payload, stream=True) as r:
        r.raise_for_status()
        for raw in r.iter_lines(decode_unicode=True):
            if not raw:
                continue
            if raw.startswith("data: "):
                data = raw[6:]
                if data.strip() == "[DONE]":
                    break
                try:
                    obj = json.loads(data)
                except Exception:
                    continue
                t = obj.get("type")
                # Yield text deltas as they arrive
                print(obj)
                if t == "response.output_text.delta":
                    # Depending on provider schema, text might be in obj["delta"]["text"] or obj["output_text"]["delta"]
                    delta = obj.get("delta", {})
                    if delta:
                        if len(delta) < 15:
                            streaming_reply += delta
                            if UI_object is not None:
                                UI_object.reply_display.setPlainText(streaming_reply)
                                QApplication.processEvents()
                                if UI_object.auto_read and not UI_object.websearch:
                                    partial_transciption += delta
                                    if streaming_reply[-1] in [".", "!", "?"]:
                                        # Look back up to the last 20 characters for a sentence end
                                        last_few = streaming_reply[-20:]
                                        # Regex: match . ! or ? not preceded and followed by a digit (not part of a number)
                                        # and followed by space or end of string
                                        match = re.search(
                                            r"(?<!\d)([.!?])(?!\d)(\s|$)", last_few
                                        )
                                        if match:
                                            # whenever you have a partial_transcription (or a completed sentence)
                                            tts_enqueue(partial_transciption)
                                            print(
                                                f"End of sentence detected in {last_few}"
                                            )
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

                    else:
                        # when a new reply starts
                        yield delta
                elif t == "response.output_text.annotation.added":
                    url = obj.get("annotation", {}).get("url")
                    title = obj.get("annotation", {}).get("title", {})
                    for key in citations.keys():
                        if url in key:
                            citations[key]["url"] = url
                            citations[key]["title"] = title

                elif t == "response.output_text.done":
                    if UI_object.websearch:

                        UI_object.reply_display.setPlainText(
                            format_web_reply(streaming_reply, citations)
                        )
                        QApplication.processEvents()

                        asyncio.run(TTS.speak_async(streaming_reply))
                    break


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


def format_web_reply(reply, citations):
    citation_block = "References:\n"
    sorted_citations = sorted(citations.items(), key=lambda x: x[1]["order"])
    for c in sorted_citations:
        citation_block += f"[{c[1]['order']}]: ({c[1]['url']}) {c[1]['title']}\n"
    return f"{reply}\n\n{citation_block}"


if __name__ == "__main__":
    # Example usage:
    messages = [
        {
            "role": "user",
            "content": [
                {
                    "type": "input_text",
                    "text": "What is the distance to the sun in different units. include citations.",
                }
            ],
        }
    ]
    reply = chat_with_gpt5_stream(messages)
    print(list(reply))
    # To send an image:
    # img_msg = attach_image_message("my_image.png", "What is in this image?")
    # messages = [img_msg]
    # reply = chat_with_gpt5(messages, model="gpt-4o")
    # print(reply["choices"][0]["message"]["content"])

    # To transcribe audio:
    # transcript = transcribe_audio("audio_sample.wav")
    # print(transcript)
