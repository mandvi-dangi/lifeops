import os
import tempfile
from sarvamai import SarvamAI

def transcribe_audio(audio_bytes: bytes):
    """Transcribe a short browser recording with Sarvam Saaras v4."""
    if not os.getenv("SARVAM_API_KEY"):
        raise RuntimeError("SARVAM_API_KEY is not configured.")
    client = SarvamAI(api_subscription_key=os.environ["SARVAM_API_KEY"])
    path = None
    try:
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            f.write(audio_bytes)
            path = f.name
        with open(path, "rb") as audio_file:
            response = client.speech_to_text.transcribe(
                file=audio_file,
                model="saaras:v4",
                language_code="unknown",
            )
        transcript = getattr(response, "transcript", None)
        language = getattr(response, "language_code", None)
        if not transcript or not transcript.strip():
            raise RuntimeError("Sarvam returned an empty transcript. Try recording again.")
        return transcript.strip(), language
    finally:
        if path and os.path.exists(path):
            os.remove(path)


def synthesize_speech(text: str) -> bytes:
    """Generate an English spoken response with Sarvam Bulbul and return WAV bytes."""
    if not os.getenv("SARVAM_API_KEY"):
        raise RuntimeError("SARVAM_API_KEY is not configured.")
    from sarvamai.play import save

    client = SarvamAI(api_subscription_key=os.environ["SARVAM_API_KEY"])
    clean_text = (text or "").strip()
    if not clean_text:
        raise RuntimeError("There is no response text to speak.")
    clean_text = clean_text[:2400]
    response = client.text_to_speech.convert(
        text=clean_text,
        model="bulbul:v4-flash",
        speaker="simran_en_customer",
        language_code="en-IN",
        output_audio_codec="wav",
    )
    path = None
    try:
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            path = f.name
        save(response, path)
        with open(path, "rb") as audio_file:
            return audio_file.read()
    finally:
        if path and os.path.exists(path):
            os.remove(path)
