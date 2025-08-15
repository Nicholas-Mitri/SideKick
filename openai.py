import os
import requests
import json, logging
import logging_config

root_logger = logging_config.setup_root_logging("openai.log")
logger = logging.getLogger(__name__)

# Get OpenAI API key from environment variable
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
# Set OpenAI API base URL
OPENAI_API_BASE = "https://api.openai.com/v1"


def openai_headers():
    """
    Returns the headers required for OpenAI API requests.
    """
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
    Sends a chat completion request to the GPT-5 API and returns the assistant's text response.

    Args:
        messages (list): List of message dicts for the conversation.
        model (str): Model name to use (default "gpt-5-mini").
        tools (list, optional): List of tools to provide to the model.
        tool_choice (str, optional): Tool selection for the model.
        max_tokens (int): Maximum number of output tokens.
        reasoning (dict, optional): Additional reasoning parameters for GPT-5.
        stream (bool): Whether to use streaming responses.

    Returns:
        str: The assistant's text response.
    """
    # Set up logging to info level if not already set
    url = f"{OPENAI_API_BASE}/responses"
    payload = {
        "model": model,
        "input": messages,
        "max_output_tokens": max_tokens,
        "stream": stream,
    }

    # Add optional parameters if provided
    if tools:
        payload["tools"] = tools
    if tool_choice:
        payload["tool_choice"] = tool_choice

    logger.info(
        f"Sending request to {url} with model={model}, tools={tools}, tool_choice={tool_choice}, max_tokens={max_tokens}, stream={stream}, reasoning={reasoning}"
    )

    try:
        response = requests.post(url, headers=openai_headers(), json=payload)
        response.raise_for_status()
    except requests.exceptions.HTTPError as e:
        logger.error(f"HTTP error occurred: {e}")
        raise
    except requests.exceptions.RequestException as e:
        logger.error(f"Request exception occurred: {e}")
        raise

    assistant_text = ""
    # Parse the assistant's output text from the response
    try:
        output_blocks = response.json().get("output", [])
        logger.info(f"Received {len(output_blocks)} output blocks from GPT-5 API.")
        for block in output_blocks:
            if block.get("role") == "assistant":
                for content in block.get("content", []):
                    if content.get("type") == "output_text":
                        assistant_text += content.get("text", "")
        logger.info("Successfully parsed assistant's text response.")
    except Exception as e:
        logger.error(f"Error parsing response JSON: {e}")
        raise

    return assistant_text


def chat_with_gpt5_stream(
    messages,
    model="gpt-5-mini",
    tools=None,
    reasoning=None,
):
    """
    Sends a streaming chat completion request to the GPT-5 API and yields response objects as they arrive.

    Args:
        messages (list): List of message dicts for the conversation.
        model (str): Model name to use (default "gpt-5-mini").
        tools (list, optional): List of tools to provide to the model.
        reasoning (dict, optional): Additional reasoning parameters for GPT-5.

    Yields:
        dict: Parsed JSON objects from the streaming response.
    """
    url = f"{OPENAI_API_BASE}/responses"
    payload = {
        "model": model,
        "input": messages,
        "stream": True,
    }

    if tools:
        payload["tools"] = tools
    # logger.debug(f"Payload: {payload}")
    logger.info(
        f"Sending streaming request to {url} with model={model}, tools={tools}, reasoning={reasoning}"
    )
    with requests.post(url, headers=openai_headers(), json=payload, stream=True) as r:
        try:
            r.raise_for_status()
        except requests.exceptions.HTTPError as e:
            # Handle HTTP errors with logging
            if r.status_code == 401:
                logger.error("HTTP 401 Unauthorized: Check your OpenAI API key.")
            elif r.status_code == 403:
                logger.error(
                    "HTTP 403 Forbidden: Check your OpenAI API key or account permissions."
                )
            else:
                logger.error(f"HTTP error occurred: {e}")
                logger.debug(f"Response content: {r.content}")
            raise
        except requests.exceptions.RequestException as e:
            logger.exception(
                "Exception occurred during OpenAI streaming request (RequestException)"
            )
            raise
        except Exception as e:
            logger.exception(
                "Unexpected exception occurred during OpenAI streaming request"
            )
            raise

        logger.info("Streaming response received, starting to process lines.")
        # Iterate over each line in the streaming response
        for raw in r.iter_lines(decode_unicode=True):
            if not raw:
                continue
            if raw.startswith("data: "):
                data = raw[6:]
                # logger.debug(f"Received streaming data chunk: {data}")
                if "response.completed" in data:
                    logger.info("Received [DONE] from streaming response.")
                    continue
                try:
                    obj = json.loads(data)
                    # logger.debug(f"Parsed streaming object: {obj}")
                    # logger.info(f"Received streaming data chunk.")
                except Exception as ex:
                    logger.warning(f"Failed to parse streaming data chunk: ({ex})")
                    continue
                yield obj


def attach_image_message(image_path):
    """
    Returns a message dict for OpenAI API with an attached image.

    Args:
        image_path (str): Path to the image file.

    Returns:
        dict: Message dict for OpenAI API, with image data encoded as base64.
    """
    logger.info(f"Attaching image from path: {image_path}")
    try:
        with open(image_path, "rb") as f:
            image_data = f.read()
        logger.info(
            f"Successfully read image file: {image_path} ({len(image_data)} bytes)"
        )
    except FileNotFoundError:
        logger.error(f"Image file not found: {image_path}")
        return {
            "type": "input_text",
            "text": "I didn't include an image. Ask me to attach it correctly.",
        }

    import base64
    import mimetypes

    def get_image_mime_type(image_path):
        """
        Returns the MIME type for the given image file path.
        """
        mime_type, _ = mimetypes.guess_type(image_path)
        return mime_type or "image/png"  # fallback

    mime_type = get_image_mime_type(image_path)

    b64_image = base64.b64encode(image_data).decode("utf-8")

    return {
        "type": "input_image",
        "image_url": f"data:{mime_type};base64,{b64_image}",
    }


def transcribe_audio(
    audio_path, model="whisper-1", language="en", prompt=None, response_format="text"
):
    url = f"{OPENAI_API_BASE}/audio/transcriptions"
    logger.info(
        f"Preparing to transcribe audio: {audio_path} with model={model}, language={language}, response_format={response_format}"
    )

    try:
        with open(audio_path, "rb") as audio_file:
            data = {
                "model": model,
                "response_format": response_format,
            }
            if language:
                data["language"] = language
            if prompt:
                data["prompt"] = prompt

            # Send multipart form-data
            response = requests.post(
                url,
                headers={
                    "Authorization": f"Bearer {OPENAI_API_KEY}"
                },  # No Content-Type here
                data=data,
                files={"file": audio_file},
            )

            if response.status_code == 400:
                logger.debug(
                    f"Transcription API 400 response content: {response.content.decode(errors='replace')}"
                )
            response.raise_for_status()

            logger.info(f"Transcription request successful for {audio_path}")

            if response_format in ("json", "verbose_json"):
                return response.json()
            return response.text

    except FileNotFoundError:
        logger.error(f"Audio file not found: {audio_path}")
        raise
    except requests.RequestException as e:
        logger.error(f"Request to OpenAI transcription API failed: {e}")
        raise
    except Exception as e:
        logger.exception(f"Unexpected error during audio transcription: {e}")
        raise


if __name__ == "__main__":

    # ------- Example usage -------:
    # Example: Basic text prompt to GPT-5
    logger.info("Starting example...")
    messages = [
        {
            "role": "user",
            "content": [
                {
                    "type": "input_text",
                    "text": "Hi",
                }
            ],
        }
    ]
    for o in chat_with_gpt5_stream(messages):
        pass

    # Example: To send an image (uncomment to use)
    # img_msg = attach_image_message("my_image.png", "What is in this image?")
    # messages = [img_msg]
    # reply = chat_with_gpt5(messages, model="gpt-4o")
    # print(reply["choices"][0]["message"]["content"])
