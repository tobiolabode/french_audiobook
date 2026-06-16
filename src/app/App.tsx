import { FormEvent, useEffect, useMemo, useState } from "react";
import {
  AudioLines,
  CircleAlert,
  CloudUpload,
  Download,
  FileAudio,
  Gauge,
  LoaderCircle,
  Play,
  SlidersHorizontal,
} from "lucide-react";
import {
  generateAudiobook,
  getConfig,
  getOneDriveStatus,
  saveToOneDrive,
  type AppConfig,
  type GeneratePayload,
  type GenerationResult,
  type OneDriveStatus,
} from "./api";
import { loadStoredGeneration, storeGeneration } from "./generatedAudioStore";

type FormState = {
  title: string;
  text: string;
  voiceId: string;
  modelId: string;
  pauseMs: number;
  speed: number;
  stability: number;
  similarity: number;
  style: number;
};

type DisplayResult = Omit<GenerationResult, "audio"> & {
  audio: Blob;
  previewUrl: string;
  downloadUrl: string;
  payload: GeneratePayload;
};

const initialForm: FormState = {
  title: "",
  text: "",
  voiceId: "",
  modelId: "",
  pauseMs: 500,
  speed: 1,
  stability: 0.5,
  similarity: 0.75,
  style: 0,
};

const sliderFormat = new Intl.NumberFormat("en", {
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
});

const logPrefix = "[FrenchAudiobook]";

export function App() {
  const [form, setForm] = useState<FormState>(initialForm);
  const [config, setConfig] = useState<AppConfig | null>(null);
  const [configError, setConfigError] = useState("");
  const [status, setStatus] = useState("Ready.");
  const [isGenerating, setIsGenerating] = useState(false);
  const [isSavingToOneDrive, setIsSavingToOneDrive] = useState(false);
  const [result, setResult] = useState<DisplayResult | null>(null);
  const [oneDriveStatus, setOneDriveStatus] = useState<OneDriveStatus | null>(null);

  const wordCount = useMemo(() => {
    return form.text.trim().split(/\s+/).filter(Boolean).length;
  }, [form.text]);

  useEffect(() => {
    let isMounted = true;
    getConfig()
      .then((nextConfig) => {
        if (!isMounted) {
          return;
        }
        setConfig(nextConfig);
        setForm((current) => ({
          ...current,
          modelId: current.modelId || nextConfig.default_model_id,
          voiceId: current.voiceId || nextConfig.default_voice_id || "",
        }));
      })
      .catch(() => {
        if (isMounted) {
          setConfigError("Local config unavailable.");
        }
      });

    return () => {
      isMounted = false;
    };
  }, []);

  useEffect(() => {
    let isMounted = true;
    loadStoredGeneration()
      .then((stored) => {
        if (!isMounted || !stored) {
          return;
        }
        const audioUrl = URL.createObjectURL(stored.audio);
        setResult({
          audio: stored.audio,
          filename: stored.filename,
          segments: stored.segments,
          previewUrl: audioUrl,
          downloadUrl: audioUrl,
          payload: stored.payload,
        });
        setForm((current) => ({
          ...current,
          title: stored.payload.title || current.title,
          text: stored.payload.text || current.text,
          voiceId: stored.payload.voice_id || current.voiceId,
          modelId: stored.payload.model_id || current.modelId,
          pauseMs: stored.payload.pause_ms,
          speed: stored.payload.speed,
          stability: stored.payload.stability,
          similarity: stored.payload.similarity_boost,
          style: stored.payload.style,
        }));
        setStatus("Restored generated audio.");
      })
      .catch((error) => {
        console.warn(`${logPrefix} Stored MP3 restore skipped`, error);
      });

    return () => {
      isMounted = false;
    };
  }, []);

  useEffect(() => {
    if (!config?.onedrive_enabled) {
      setOneDriveStatus(null);
      return;
    }

    let isMounted = true;
    getOneDriveStatus()
      .then((status) => {
        if (isMounted) {
          setOneDriveStatus(status);
        }
      })
      .catch((error) => {
        if (isMounted) {
          setOneDriveStatus({ enabled: false, connected: false });
          console.error(`${logPrefix} OneDrive status request failed`, error);
        }
      });

    return () => {
      isMounted = false;
    };
  }, [config?.onedrive_enabled]);

  useEffect(() => {
    return () => {
      if (result) {
        URL.revokeObjectURL(result.previewUrl);
      }
    };
  }, [result]);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setIsGenerating(true);
    setResult(null);
    setStatus("Generating audio...");
    const payload = buildGeneratePayload(form);
    console.info(`${logPrefix} Generate MP3 submitted`, {
      titleProvided: Boolean(form.title.trim()),
      textLength: form.text.length,
      wordCount,
      voiceProvided: Boolean(form.voiceId.trim()),
      modelId: form.modelId,
      pauseMs: form.pauseMs,
      speed: form.speed,
      stability: form.stability,
      similarity: form.similarity,
      style: form.style,
    });

    try {
      const nextResult = await generateAudiobook(payload);
      const audioUrl = URL.createObjectURL(nextResult.audio);
      setResult({
        audio: nextResult.audio,
        filename: nextResult.filename,
        segments: nextResult.segments,
        previewUrl: audioUrl,
        downloadUrl: audioUrl,
        payload,
      });
      storeGeneration({
        audio: nextResult.audio,
        filename: nextResult.filename,
        segments: nextResult.segments,
        payload,
      }).catch((error) => {
        console.warn(`${logPrefix} Stored MP3 save skipped`, error);
      });
      setStatus("Generated successfully.");
      console.info(`${logPrefix} MP3 ready`, {
        filename: nextResult.filename,
        segments: nextResult.segments,
        bytes: nextResult.audio.size,
      });
    } catch (error) {
      setStatus(error instanceof Error ? error.message : "Generation failed.");
      console.error(`${logPrefix} Generate MP3 failed`, error);
    } finally {
      setIsGenerating(false);
      console.info(`${logPrefix} Generate MP3 finished`);
    }
  }

  async function handleSaveToOneDrive() {
    if (!result) {
      return;
    }

    setIsSavingToOneDrive(true);
    setStatus("Saving to OneDrive...");
    try {
      const saved = await saveToOneDrive(result.audio, result.filename);
      setStatus(`Saved to OneDrive: ${saved.name}`);
      setOneDriveStatus({ enabled: true, connected: true });
    } catch (error) {
      const message = error instanceof Error ? error.message : "OneDrive save failed.";
      if (message.toLowerCase().includes("auth")) {
        setOneDriveStatus({ enabled: true, connected: false });
      }
      setStatus(message);
      console.error(`${logPrefix} OneDrive save failed`, error);
    } finally {
      setIsSavingToOneDrive(false);
    }
  }

  const configMessage = config
    ? config.missing_required.length > 0
        ? `Set ${config.missing_required.join(", ")} in .env to enable generation.`
      : config.has_default_voice
        ? "Default voice is ready."
        : "Enter a Voice ID or set ELEVENLABS_DEFAULT_VOICE_ID."
    : configError || "Checking local config...";
  const needsVoiceId = Boolean(config && !config.has_default_voice);
  const missingServerConfig = Boolean(config && config.missing_required.length > 0);
  const canGenerate = Boolean(config) && !missingServerConfig;

  return (
    <main className="app-shell">
      <section className="workspace" aria-label="Audiobook generator">
        <div className="editor-panel">
          <header className="app-header">
            <div className="brand-mark" aria-hidden="true">
              <AudioLines size={28} />
            </div>
            <div>
              <h1>French Audiobook</h1>
              <p>Build a listening track from French text.</p>
            </div>
          </header>

          <form className="generation-form" onSubmit={handleSubmit}>
            <div className="field-grid">
              <label>
                <span>Title</span>
                <input
                  name="title"
                  type="text"
                  value={form.title}
                  placeholder="Lecon du jour"
                  onChange={(event) => setForm({ ...form, title: event.target.value })}
                />
              </label>
              <label>
                <span>Model ID</span>
                <input
                  name="model_id"
                  type="text"
                  value={form.modelId}
                  placeholder={config?.default_model_id || "eleven_multilingual_v2"}
                  onChange={(event) => setForm({ ...form, modelId: event.target.value })}
                />
              </label>
            </div>

            <label>
              <span>French text</span>
              <textarea
                name="text"
                rows={13}
                required
                value={form.text}
                placeholder="Bonjour..."
                onChange={(event) => setForm({ ...form, text: event.target.value })}
              />
            </label>

            <div className="form-bar">
              <span>{wordCount} {wordCount === 1 ? "word" : "words"}</span>
              <span>{configMessage}</span>
            </div>

            <div className="field-grid voice-row">
              <label>
                <span>Voice ID</span>
                <input
                  name="voice_id"
                  type="text"
                  required={needsVoiceId}
                  value={form.voiceId}
                  placeholder="Use configured default"
                  onChange={(event) => setForm({ ...form, voiceId: event.target.value })}
                />
              </label>
              <label>
                <span>Pause</span>
                <input
                  name="pause_ms"
                  type="number"
                  min={0}
                  max={3000}
                  step={50}
                  value={form.pauseMs}
                  onChange={(event) => setForm({ ...form, pauseMs: Number(event.target.value) })}
                />
              </label>
            </div>

            <fieldset className="voice-tuning">
              <legend>
                <SlidersHorizontal size={18} aria-hidden="true" />
                Voice tuning
              </legend>
              <RangeField
                label="Speed"
                min={0.7}
                max={1.2}
                step={0.05}
                value={form.speed}
                onChange={(speed) => setForm({ ...form, speed })}
              />
              <RangeField
                label="Stability"
                min={0}
                max={1}
                step={0.05}
                value={form.stability}
                onChange={(stability) => setForm({ ...form, stability })}
              />
              <RangeField
                label="Similarity"
                min={0}
                max={1}
                step={0.05}
                value={form.similarity}
                onChange={(similarity) => setForm({ ...form, similarity })}
              />
              <RangeField
                label="Style"
                min={0}
                max={1}
                step={0.05}
                value={form.style}
                onChange={(style) => setForm({ ...form, style })}
              />
            </fieldset>

            <button
              aria-busy={isGenerating}
              className="primary-action"
              data-generating={isGenerating ? "true" : "false"}
              type="submit"
              disabled={isGenerating || !canGenerate}
            >
              {isGenerating ? <LoaderCircle className="spin" size={20} /> : <FileAudio size={20} />}
              {isGenerating ? "Generating MP3" : "Generate MP3"}
            </button>
          </form>
        </div>

        <aside className="result-panel" aria-live="polite">
          <div className="result-heading">
            <Play size={20} aria-hidden="true" />
            <h2>Output</h2>
          </div>

          <p className={result ? "status success" : status === "Ready." ? "status" : "status attention"}>
            {!result && status !== "Ready." ? <CircleAlert size={18} aria-hidden="true" /> : null}
            {status}
          </p>

          {result ? (
            <>
              <audio aria-label="Generated audio preview" controls src={result.previewUrl} />
              <a className="download-link" href={result.downloadUrl} download={result.filename}>
                <Download size={18} aria-hidden="true" />
                Download MP3
              </a>
              {config?.onedrive_enabled ? (
                oneDriveStatus?.connected ? (
                  <button
                    className="download-link secondary-action"
                    type="button"
                    onClick={handleSaveToOneDrive}
                    disabled={isSavingToOneDrive}
                  >
                    {isSavingToOneDrive ? (
                      <LoaderCircle className="spin" size={18} aria-hidden="true" />
                    ) : (
                      <CloudUpload size={18} aria-hidden="true" />
                    )}
                    {isSavingToOneDrive ? "Saving to OneDrive" : "Save to OneDrive"}
                  </button>
                ) : (
                  <a className="download-link secondary-action" href="/api/auth/microsoft/start">
                    <CloudUpload size={18} aria-hidden="true" />
                    Connect OneDrive
                  </a>
                )
              ) : null}
              <dl className="metadata">
                <dt>Filename</dt>
                <dd>{result.filename}</dd>
                <dt>Segments</dt>
                <dd>{result.segments}</dd>
              </dl>
            </>
          ) : (
            <div className="empty-state">
              <Gauge size={24} aria-hidden="true" />
              <span>Ready for the next track.</span>
            </div>
          )}
        </aside>
      </section>
    </main>
  );
}

function buildGeneratePayload(form: FormState): GeneratePayload {
  return {
    title: form.title,
    text: form.text,
    voice_id: form.voiceId,
    model_id: form.modelId,
    pause_ms: form.pauseMs,
    speed: form.speed,
    stability: form.stability,
    similarity_boost: form.similarity,
    style: form.style,
  };
}

type RangeFieldProps = {
  label: string;
  min: number;
  max: number;
  step: number;
  value: number;
  onChange: (value: number) => void;
};

function RangeField({ label, min, max, step, value, onChange }: RangeFieldProps) {
  return (
    <label className="range-field">
      <span>
        {label}
        <output>{sliderFormat.format(value)}</output>
      </span>
      <input
        aria-label={label}
        type="range"
        min={min}
        max={max}
        step={step}
        value={value}
        onChange={(event) => onChange(Number(event.target.value))}
      />
    </label>
  );
}
