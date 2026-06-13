export type AppConfig = {
  default_model_id: string;
  has_default_voice: boolean;
  output_dir: string;
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
  path: string;
  download_url: string;
  preview_url: string;
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
  return readJson<GenerationResult>(response);
}
