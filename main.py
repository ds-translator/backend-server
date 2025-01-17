import os
import base64
from dotenv import load_dotenv
import tempfile
from pathlib import Path
from json import dumps as json_dumps, loads as json_loads

from fastapi import FastAPI, WebSocket
from openai import OpenAI
import deepl

load_dotenv() or None

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
DEEPL_API_KEY = os.getenv("DEEPL_API_KEY")
TRANSLATOR_ENGINE = os.getenv("TRANSLATOR_ENGINE")

client = OpenAI()

app = FastAPI()

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()

    print("Client connected via WebSocket.")

    while True:
        try:
            message = await websocket.receive_text()
            data = None
            try:
                data = json_loads(message)
            except Exception as e:
                print("Error decoding JSON:", e)
                continue

            password = data.get("password")
            if password != "ds":
                print("Wrong password")
                await websocket.send_text(
                    json_dumps(
                        {
                            "event": "authentication_error",
                            "text": "Please check the password",
                        }
                    )
                )
                continue

            language = data.get("language")

            event_type = data.get("event")

            if event_type == "audio_blob":
                print("receiving audio blob")
                audio_base64 = data.get("audioBase64")
                if not audio_base64:
                    continue

                # each browser will record in another audio format
                mime_type = data.get("mimeType")
                if not mime_type:
                    continue

                audio_bytes = base64.b64decode(audio_base64)

                with tempfile.NamedTemporaryFile(
                    suffix=get_file_extension(mime_type), delete=False
                ) as tmp:
                    tmp.write(audio_bytes)
                    tmp_path = tmp.name

                translated_text = ""
                transcription = ""

                try:
                    # send to whisper for transcription
                    audio_file = open(tmp_path, "rb")
                    transcription = client.audio.transcriptions.create(
                        model="whisper-1", file=audio_file
                    )

                    print(transcription.text)

                    # translate the transcription
                    if TRANSLATOR_ENGINE == "deepl":
                        translator = deepl.Translator(DEEPL_API_KEY)

                        result = translator.translate_text(
                            transcription.text, target_lang=language
                        )

                        translated_text = result.text

                        print("Translated text:", translated_text)
                    else:
                        completion = client.chat.completions.create(
                            model="gpt-4o-mini",
                            messages=[
                                {
                                    "role": "system",
                                    "content": "You are professional translator.",
                                },
                                {
                                    "role": "user",
                                    "content": "The target language is the iso code "
                                    + language
                                    + ". Please translate this:\n\n"
                                    + transcription.text
                                    + "\n\nTranslation:",
                                },
                            ],
                        )
                        translated_text = completion.choices[0].message
                        translated_text = translated_text.content

                    print(translated_text)

                    # send the translation as text to the browser
                    await websocket.send_text(
                        json_dumps(
                            {
                                "event": "transcript_result",
                                "text": f"Translated: {translated_text}",
                            }
                        )
                    )

                    # create a speech audio from the transcription
                    speech_file_path = Path(__file__).parent / "speech.mp3"
                    response = client.audio.speech.create(
                        model="tts-1", voice="coral", input=translated_text, speed=0.85
                    )
                    response.stream_to_file(speech_file_path)

                    with open(speech_file_path, "rb") as f:
                        tts_audio_bytes = f.read()
                    encoded_tts_audio = base64.b64encode(tts_audio_bytes).decode(
                        "utf-8"
                    )

                    # send the translation speech to the browser
                    await websocket.send_text(
                        json_dumps(
                            {
                                "event": "tts_audio",
                                "audioBase64": encoded_tts_audio,
                                "contentType": "audio/mp3",
                            }
                        )
                    )
                except Exception as e:
                    print("Error in processing audio:", e)

        except Exception as e:
            print("WebSocket disconnected or error:", e)
            break


def get_file_extension(mime_type):
    mime_to_extension = {
        "audio/webm": ".webm",
        "audio/mp4": ".mp4",
        "audio/mp3": ".mp3",
        "audio/wav": ".wav",
        "audio/ogg": ".ogg",
    }
    return mime_to_extension.get(mime_type, "Unknown MIME type")



