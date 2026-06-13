# French Audiobook

React app plus Python backend for turning French text into generated MP3 audiobook files.

## Requirements

- Python 3.11+
- Node.js 20.19+ or 22.12+ and npm
- An ElevenLabs API key for real MP3 generation
- A local output directory for generated MP3 files

## Configuration

Copy `.env.example` to `.env` and fill in the values for generation:

```env
ELEVENLABS_API_KEY=
ELEVENLABS_DEFAULT_VOICE_ID=
ELEVENLABS_DEFAULT_MODEL_ID=eleven_multilingual_v2
ONEDRIVE_AUDIO_DIR=
HOST=127.0.0.1
PORT=8000
```

The browser app never receives `ELEVENLABS_API_KEY`; generation stays behind the Python API. The app can start without the key and will show which local settings are missing, but generating real audio requires `ELEVENLABS_API_KEY`, `ONEDRIVE_AUDIO_DIR`, and either `ELEVENLABS_DEFAULT_VOICE_ID` or a Voice ID entered in the form.

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

Open `http://127.0.0.1:5173`. Vite proxies `/api` and `/downloads` to the Python backend on port `8000`.

## Build

```powershell
npm run build
```

The build writes the React bundle to `src/french_audiobook/static`, which lets the Python backend serve the compiled app.

## Tests

```powershell
$env:PYTHONPATH="src"
pytest
npm test
```
