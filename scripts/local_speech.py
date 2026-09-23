"""Loopback-only OpenAI-compatible transcription server for the MedX Voice Agent.

    python3 scripts/local_speech.py            # http://127.0.0.1:9100/v1/audio/transcriptions

Audio never leaves the machine (DEC-0006). Uses the installed faster-whisper; the model
is downloaded on first run (FRONT_DOOR_SPEECH_LOCAL_MODEL, default "small").
"""
import os
import tempfile
from fastapi import FastAPI, File, Form, UploadFile

MODEL = os.environ.get('FRONT_DOOR_SPEECH_LOCAL_MODEL', 'small')
app = FastAPI(title='MedX local speech')
_model = None


def model():
    global _model
    if _model is None:
        from faster_whisper import WhisperModel
        _model = WhisperModel(MODEL, device='cpu', compute_type='int8')
    return _model


@app.post('/v1/audio/transcriptions')
async def transcribe(file: UploadFile = File(...), language: str = Form('th'), model_name: str = Form('', alias='model')):
    with tempfile.NamedTemporaryFile(suffix='.' + (file.filename or 'a.webm').rsplit('.', 1)[-1]) as audio:
        audio.write(await file.read())
        audio.flush()
        segments, _ = model().transcribe(audio.name, language=language or 'th', vad_filter=True)
        return {'text': ' '.join(s.text.strip() for s in segments).strip() or '(ไม่ได้ยินเสียงพูด)'}


if __name__ == '__main__':
    import uvicorn
    uvicorn.run(app, host='127.0.0.1', port=int(os.environ.get('FRONT_DOOR_SPEECH_LOCAL_PORT', '9100')))
