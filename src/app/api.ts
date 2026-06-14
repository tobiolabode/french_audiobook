export type AppConfig = {
  default_model_id: string;
  has_default_voice: boolean;
  storage_mode: "direct_response";
  missing_required: string[];
};

export type GeneratePayload = {
  title: string;
  text: string;
  voice_id: string;
  model_id: string;
  pause_ms: number;
  speed: number;
  stability: number;
  similarity_boost: number;
  style: number;
};

export type GenerationResult = {
  audio: Blob;
  filename: string;
  segments: number;
};

type ApiErrorPayload = {
  error?: string;
};

const GENERATE_TIMEOUT_MS = 120_000;
const logPrefix = "[FrenchAudiobook]";

async function readJson<T>(response: Response): Promise<T> {
  const payload = (await response.json()) as T & ApiErrorPayload;
  if (!response.ok) {
    throw new Error(payload.error || "The request failed.");
  }
  return payload;
}

export async function getConfig(): Promise<AppConfig> {
  console.info(`${logPrefix} Loading app config`);
  try {
    const response = await fetch("/api/config");
    const config = await readJson<AppConfig>(response);
    console.info(`${logPrefix} Config loaded`, {
      hasDefaultVoice: config.has_default_voice,
      missingRequired: config.missing_required,
      storageMode: config.storage_mode,
    });
    return config;
  } catch (error) {
    console.error(`${logPrefix} Config request failed`, error);
    throw error;
  }
}

export async function generateAudiobook(payload: GeneratePayload): Promise<GenerationResult> {
  const controller = new AbortController();
  const timeoutId = window.setTimeout(() => controller.abort(), GENERATE_TIMEOUT_MS);

  console.info(`${logPrefix} Starting MP3 generation request`, {
    titleProvided: Boolean(payload.title.trim()),
    textLength: payload.text.length,
    voiceProvided: Boolean(payload.voice_id.trim()),
    modelId: payload.model_id,
    pauseMs: payload.pause_ms,
  });

  try {
    const response = await fetch("/api/generate", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(payload),
      signal: controller.signal,
    });
    console.info(`${logPrefix} MP3 generation response received`, {
      ok: response.ok,
      status: response.status,
      contentType: response.headers.get("content-type"),
      segments: response.headers.get("x-audiobook-segments"),
    });

    if (!response.ok) {
      const errorPayload = (await response.json().catch(() => ({}))) as ApiErrorPayload;
      throw new Error(errorPayload.error || "The request failed.");
    }

    const contentType = response.headers.get("content-type") || "";
    if (!contentType.includes("audio/mpeg")) {
      throw new Error("Generation did not return an MP3 response.");
    }

    const audio = await response.blob();
    if (audio.size === 0) {
      throw new Error("Generation returned an empty MP3.");
    }

    return {
      audio,
      filename: filenameFromContentDisposition(response.headers.get("content-disposition")),
      segments: Number(response.headers.get("x-audiobook-segments") || "0"),
    };
  } catch (error) {
    if (error instanceof DOMException && error.name === "AbortError") {
      console.error(`${logPrefix} MP3 generation timed out after ${GENERATE_TIMEOUT_MS}ms`);
      throw new Error("Generation timed out. Try shorter text or check the server logs.");
    }
    console.error(`${logPrefix} MP3 generation request failed`, error);
    throw error;
  } finally {
    window.clearTimeout(timeoutId);
  }
}

function filenameFromContentDisposition(value: string | null): string {
  if (!value) {
    return "french-audiobook.mp3";
  }
  const match = /filename="?([^";]+)"?/i.exec(value);
  return match?.[1] || "french-audiobook.mp3";
}
