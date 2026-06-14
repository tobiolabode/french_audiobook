# French Audiobook

React app plus Python API functions for turning French text into generated MP3 audiobook files.

## Requirements

- Python 3.11+
- Node.js 20.19+ or 22.12+ and npm
- An ElevenLabs API key for real MP3 generation
- A local output directory only if you use the legacy file-writing helper

## Configuration

Copy `.env.example` to `.env` and fill in the values for local generation:

```env
ELEVENLABS_API_KEY=
ELEVENLABS_DEFAULT_VOICE_ID=
ELEVENLABS_DEFAULT_MODEL_ID=eleven_multilingual_v2
ONEDRIVE_AUDIO_DIR=
HOST=127.0.0.1
PORT=8000
```

The browser app never receives `ELEVENLABS_API_KEY`; generation stays behind the Python API. The app can start without the key and will show which settings are missing, but generating real audio requires `ELEVENLABS_API_KEY` and either `ELEVENLABS_DEFAULT_VOICE_ID` or a Voice ID entered in the form.

Generated MP3s are streamed directly back from `/api/generate`. The deployed app does not write generated audio to Vercel's filesystem and does not need a `/downloads` route.

## Local Development

Start the Python API:

```powershell
$env:PYTHONPATH="src"
python -m french_audiobook.app
```

Start the React app in another terminal:

```powershell
npm install
npm run dev
```

Open `http://127.0.0.1:5173`. Vite proxies `/api` to the Python backend on port `8000`.

## Build

```powershell
npm run build
```

The build writes the React bundle to `dist`, which is the folder Vercel publishes.

## Vercel Deployment

This repository is configured as a Vite static app with Python Serverless Functions:

- `vercel.json` runs `npm run build` and publishes `dist`.
- `/api/config` reports non-secret runtime readiness.
- `/api/generate` calls ElevenLabs server-side and returns an `audio/mpeg` response directly.

Set these environment variables in the Vercel project:

```env
ELEVENLABS_API_KEY=
ELEVENLABS_DEFAULT_VOICE_ID=
ELEVENLABS_DEFAULT_MODEL_ID=eleven_multilingual_v2
```

`ONEDRIVE_AUDIO_DIR` is not required on Vercel. It is only used by the Python generator's legacy local file-writing method.

## Tests

```powershell
$env:PYTHONPATH="src"
pytest
npm test
```
