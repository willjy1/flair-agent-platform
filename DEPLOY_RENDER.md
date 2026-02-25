# Deploy To Render (Fastest Public Link)

This repo includes `render.yaml`, so Render can create the service with the right start command automatically.

## 3-Step Setup

1. Push `C:\Users\willi\flair-agent-platform` to a GitHub repo.

2. In Render, click **New +** -> **Blueprint** and connect that repo.

3. After deploy finishes, open and send:
   - `https://<your-render-service>.onrender.com/support`

## Optional (recommended for better demo quality)

Add these environment variables in Render (Service -> Environment):

- `OPENAI_API_KEY`
- `ELEVENLABS_API_KEY`
- `ELEVENLABS_VOICE_ID`
- `ELEVENLABS_MODEL_ID=eleven_multilingual_v2`

Optional voice fallback:
- `OPENAI_TTS_MODEL=gpt-4o-mini-tts`
- `OPENAI_TTS_VOICE=marin`

Optional LLM model:
- `DEFAULT_MODEL=gpt-5.2` (only if your OpenAI account supports it)

## Notes

- The app will still run without API keys (heuristic/demo mode), but voice and conversation quality are better with keys configured.
- Local JSON stores are mapped to `/tmp` in Render for demo use.
- This is a customer-facing demo/support experience at:
  - `/support`

## One-Click Link Template (after GitHub repo exists)

If your repo is public, you can use Render's deploy URL format:

`https://render.com/deploy?repo=<YOUR_GITHUB_REPO_URL>`

Example:

`https://render.com/deploy?repo=https://github.com/yourname/flair-agent-platform`
