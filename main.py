import os
import base64
from dotenv import load_dotenv
import tempfile
from pathlib import Path
from json import dumps as json_dumps, loads as json_loads

from fastapi import FastAPI, WebSocket, Response
from openai import OpenAI
import deepl

import time
import ffmpeg
import requests

import boto3

load_dotenv() or None

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_API_URL = os.getenv("OPENAI_API_URL", 'https://api.openai.com/v1')
STT_API_URL = os.getenv("STT_API_URL", 'https://api.openai.com/v1')
TTS_API_URL = os.getenv("TTS_API_URL", 'https://api.openai.com/v1')
WHISPER_MODEL = os.getenv("WHISPER_MODEL", "whisper-1")
DEEPL_API_KEY = os.getenv("DEEPL_API_KEY")
TRANSLATOR_ENGINE = os.getenv("TRANSLATOR_ENGINE", "deepl")
SPEECH_TO_TEXT_ENGINE = os.getenv("SPEECH_TO_TEXT_ENGINE", "whisper_stt")
TEXT_TO_SPEECH_ENGINE = os.getenv("TEXT_TO_SPEECH_ENGINE", "whisper_tts")


print("OPENAI_API_URL:", OPENAI_API_URL)
print("STT_API_URL:", STT_API_URL)
print("TTS_API_URL:", TTS_API_URL)
print("WHISPER_MODEL:", WHISPER_MODEL)
print("TRANSLATOR_ENGINE:", TRANSLATOR_ENGINE)
print("SPEECH_TO_TEXT_ENGINE:", SPEECH_TO_TEXT_ENGINE)
print("TEXT_TO_SPEECH_ENGINE:", TEXT_TO_SPEECH_ENGINE)

stt_client = OpenAI(
    base_url=STT_API_URL
)

tts_client = OpenAI(
    base_url=TTS_API_URL
)

client = OpenAI(
    base_url=OPENAI_API_URL
)

app = FastAPI()

@app.get("/")
async def read_root():
    return Response(status_code=204)

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
                    tmp.flush()
                    # tmp_path = tmp.name

                local_audio_dir = "saved_audio"
                os.makedirs(local_audio_dir, exist_ok=True)

                # Generate a unique filename using a timestamp.
                audio_filename = f"audio_{int(time.time())}{get_file_extension(mime_type)}"
                local_audio_path = os.path.join(local_audio_dir, audio_filename)

                # Write the audio bytes to the file.
                with open(local_audio_path, "wb") as local_audio_file:
                    local_audio_file.write(audio_bytes)

                print("Saved audio locally at:", local_audio_path)

                # Generate a unique filename for the WAV file.
                wav_filename = f"audio_{int(time.time())}.wav"
                wav_audio_path = os.path.join(local_audio_dir, wav_filename)

                # Use ffmpeg-python to transcode the audio file to WAV.
                try:
                    (
                        ffmpeg
                        .input(local_audio_path)
                        .output(wav_audio_path)
                        .overwrite_output()  # This will overwrite the file if it already exists.
                        .run(quiet=True)
                    )
                    print("Transcoded to WAV at:", wav_audio_path)
                except ffmpeg.Error as e:
                    print("Error transcoding audio:", e)


                translated_text = ""
                transcription = ""

                try:
                    # send to whisper for transcription
                    audio_file = open(wav_audio_path, "rb")
                    transcription = stt_client.audio.transcriptions.create(
                        model=WHISPER_MODEL, file=audio_file
                    )

                    print(transcription.text)

                    # translate the transcription
                    if TRANSLATOR_ENGINE == "deepl":
                        translator = deepl.Translator(DEEPL_API_KEY)

                        result = translator.translate_text(
                            transcription.text, target_lang=language
                        )
                        # language = result.detected_source_lang
                        translated_text = result.text



                        print("Translated text:", translated_text)
                        # print("Detected language:", language)
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
                    speech_file_path = Path(__file__).parent / "speech.mp3"

                    if TEXT_TO_SPEECH_ENGINE == "whisper_tts":
                        # create a speech audio from the transcription
                        
                        response = tts_client.audio.speech.create(
                            model="tts-1", voice="coral", input=translated_text, speed=0.85
                        )
                        response.stream_to_file(speech_file_path)

                    kokoro_language_mapping = {
                        "ES": "e",
                        "FR": "f",
                        "IN": "h",
                        "IT": "i",
                        "PT": "p",
                        "EN": "a",
                        "JA": "j",
                        "ZH": "z"
                    }

                    kokoro_voice_mapping = {
                        "ES": "ef_dora",
                        "FR": "ff_siwis",
                        "IN": "hf_alpha",
                        "IT": "if_sara",
                        "PT": "pm_alex",
                        "EN": "af_bella",
                        "JA": "jf_tebukuro",
                        "ZH": "zf_xiaobei"
                    }                    
                    
                    if language.upper() == "EN-US":
                        language = "EN"
                    
                    voice_choice = kokoro_voice_mapping[language.upper()]
                    language_choice = kokoro_language_mapping[language.upper()]

                    print("language choice:", language_choice)


                    if TEXT_TO_SPEECH_ENGINE == "kokoro":
                        response = requests.post(
                            TTS_API_URL + "/audio/speech",
                            json={
                                "model": "kokoro",  
                                "input": translated_text,
                                "voice": voice_choice,
                                "response_format": "mp3",  # Supported: mp3, wav, opus, flac
                                "speed": 1.0,
                                "lang_code": language_choice
                            }
                        )
                        with open(speech_file_path, "wb") as f:
                            f.write(response.content)

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



