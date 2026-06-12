# French Audiobook Learning Tool Plan

## Summary

Build a local web app that turns pasted French learning text into downloadable MP3 audiobooks using ElevenLabs Text to Speech. The app will preserve the useful controls from the existing French TTS Tool: pacing, pause between lines or sections, audio preview, download, and saving generated files into a configured local OneDrive-synced folder.

The app should also be designed for hosting on Vercel. The browser frontend can be served publicly, while secret-handling API routes or backend functions must keep the ElevenLabs API key out of client-side code, source files, logs, and commits.

The ElevenLabs API key that was pasted into chat must be treated as sensitive and should not be committed. Use a replacement key stored only in local or Vercel environment variables.

## Key Changes

- Create a small full-stack web app:
  - React/Vite or Next.js frontend for text input, voice/model controls, pacing controls, pause controls, preview, download, and generation status.
  - Backend API for ElevenLabs calls, file writing, download handling, and OneDrive path handling.
- Prefer a Vercel-friendly architecture:
  - Use environment variables for `ELEVENLABS_API_KEY`, default voice/model IDs, and output settings.
  - Keep API calls server-side so the key is never exposed to browser JavaScript.
  - Document local development and Vercel deployment setup.
- Use ElevenLabs Text to Speech:
  - `POST /v1/text-to-speech/:voice_id`
  - `xi-api-key` read from `ELEVENLABS_API_KEY`
  - default `model_id=eleven_multilingual_v2`
  - `language_code=fr`
  - default `output_format=mp3_44100_128`
- Add local configuration through `.env.example`:
  - `ELEVENLABS_API_KEY=`
  - `ELEVENLABS_DEFAULT_VOICE_ID=`
  - `ELEVENLABS_DEFAULT_MODEL_ID=eleven_multilingual_v2`
  - `ONEDRIVE_AUDIO_DIR=`
- Implement output behavior:
  - Validate that text is non-empty.
  - Split pasted text by non-empty lines as audiobook segments.
  - Send each segment to ElevenLabs.
  - Combine generated MP3 segments with configurable silence between them.
  - Save the final MP3 with a sanitized timestamped filename.
  - Return metadata plus a download URL.
- Keep voice/model flexible:
  - Show configured defaults in the UI.
  - Let the user override voice ID, model ID, voice tuning, playback speed target, pause milliseconds, and output title.
  - Do not build a voice-list dropdown in v1.

## Tests

- Use pytest or the repo's selected test framework for backend behavior:
  - Reject empty text.
  - Sanitize output filenames.
  - Save generated audio into the configured OneDrive directory during local runs.
  - Never log or return the API key.
  - Mock ElevenLabs and verify request shape: voice ID, model ID, French language code, and text payload.
- Add frontend smoke coverage:
  - Form renders.
  - Generate button disables while submitting.
  - Successful response displays preview and download links.
- Manual acceptance:
  - Start the local dev app.
  - Paste two or more French lines.
  - Generate audio.
  - Confirm MP3 appears in the configured OneDrive folder locally.
  - Confirm browser preview and download work.
  - Deploy to Vercel with environment variables configured and confirm generation works without exposing secrets.

## Assumptions

- v1 uses pasted text only; no AI lesson-script generation and no file upload.
- v1 saves to a local OneDrive-synced folder during local development.
- Hosted Vercel output may use browser download or later cloud storage, because Vercel functions cannot reliably write to a user's local OneDrive folder.
- The backend owns all ElevenLabs calls so the API key is never exposed to the browser.
- The pasted key should be rotated before real use.
- No commits should include secrets, generated MP3s, `.env`, or OneDrive outputs.
