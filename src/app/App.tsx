import { FormEvent, useEffect, useMemo, useState } from "react";
import {
  AudioLines,
  CircleAlert,
  Download,
  FileAudio,
  Gauge,
  LoaderCircle,
  Play,
  SlidersHorizontal,
} from "lucide-react";
import { generateAudiobook, getConfig, type AppConfig, type GenerationResult } from "./api";

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
  previewUrl: string;
  downloadUrl: string;
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

export function App() {
  const [form, setForm] = useState<FormState>(initialForm);
  const [config, setConfig] = useState<AppConfig | null>(null);
  const [configError, setConfigError] = useState("");
  const [status, setStatus] = useState("Ready.");
  const [isGenerating, setIsGenerating] = useState(false);
  const [result, setResult] = useState<DisplayResult | null>(null);

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

    try {
      const nextResult = await generateAudiobook({
        title: form.title,
        text: form.text,
        voice_id: form.voiceId,
        model_id: form.modelId,
        pause_ms: form.pauseMs,
        speed: form.speed,
        stability: form.stability,
        similarity_boost: form.similarity,
        style: form.style,
      });
      const audioUrl = URL.createObjectURL(nextResult.audio);
      setResult({
        filename: nextResult.filename,
        segments: nextResult.segments,
        previewUrl: audioUrl,
        downloadUrl: audioUrl,
      });
      setStatus("Generated successfully.");
    } catch (error) {
      setStatus(error instanceof Error ? error.message : "Generation failed.");
    } finally {
      setIsGenerating(false);
    }
  }

  const configMessage = config
    ? config.missing_required.length > 0
      ? `Set ${config.missing_required.join(", ")} in .env to enable generation.`
      : config.has_default_voice
        ? "Generated MP3s stream directly to this browser."
        : "Enter a Voice ID or set ELEVENLABS_DEFAULT_VOICE_ID."
    : configError || "Checking local config...";
  const needsVoiceId = Boolean(config && !config.has_default_voice);
  const missingServerConfig = Boolean(config && config.missing_required.length > 0);
  const canGenerate = Boolean(config) && !missingServerConfig && (!needsVoiceId || Boolean(form.voiceId.trim()));

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

            <button className="primary-action" type="submit" disabled={isGenerating || !canGenerate}>
              {isGenerating ? <LoaderCircle className="spin" size={20} /> : <FileAudio size={20} />}
              Generate MP3
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
