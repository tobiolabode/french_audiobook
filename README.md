Internal tool to create French audiobooks and podcasts for learning.

## Local app

1. Create a local `.env` from `.env.example` and fill in:
   - `ELEVENLABS_API_KEY`
   - `ELEVENLABS_DEFAULT_VOICE_ID`
   - `ONEDRIVE_AUDIO_DIR`
2. Start the app:

```bash
set -a
source .env
set +a
python -m french_audiobook.app
```

3. Open `http://127.0.0.1:8000`.

The API key is read only on the server. Generated MP3 files are written to
`ONEDRIVE_AUDIO_DIR`, and preview/download links serve files from that directory.

## Tests

```bash
pytest
```
