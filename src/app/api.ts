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

async function readJson<T>(response: Response): Promise<T> {
  const payload = (await response.json()) as T & ApiErrorPayload;
  if (!response.ok) {
    throw new Error(payload.error || "The request failed.");
  }
  return payload;
}

export async function getConfig(): Promise<AppConfig> {
  const response = await fetch("/api/config");
  return readJson<AppConfig>(response);
}

export async function generateAudiobook(payload: GeneratePayload): Promise<GenerationResult> {
  const response = await fetch("/api/generate", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!response.ok) {
    const errorPayload = (await response.json().catch(() => ({}))) as ApiErrorPayload;
    throw new Error(errorPayload.error || "The request failed.");
  }

  return {
    audio: await response.blob(),
    filename: filenameFromContentDisposition(response.headers.get("content-disposition")),
    segments: Number(response.headers.get("x-audiobook-segments") || "0"),
  };
}

function filenameFromContentDisposition(value: string | null): string {
  if (!value) {
    return "french-audiobook.mp3";
  }
  const match = /filename="?([^";]+)"?/i.exec(value);
  return match?.[1] || "french-audiobook.mp3";
}
