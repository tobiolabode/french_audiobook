import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { StoredGenerationResult } from "../../src/app/generatedAudioStore";
import { App } from "../../src/app/App";
import { loadStoredGeneration, storeGeneration } from "../../src/app/generatedAudioStore";

vi.mock("../../src/app/generatedAudioStore", () => ({
  loadStoredGeneration: vi.fn(async () => null),
  storeGeneration: vi.fn(async () => undefined),
}));

describe("App", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    vi.mocked(loadStoredGeneration).mockResolvedValue(null);
    vi.mocked(storeGeneration).mockResolvedValue(undefined);
    vi.stubGlobal(
      "URL",
      Object.assign(URL, {
        createObjectURL: vi.fn(() => "blob:generated-audio"),
        revokeObjectURL: vi.fn(),
      }),
    );
  });

  it("shows the audiobook generation workflow on the first screen", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValueOnce(
      new Response(
          JSON.stringify({
            default_model_id: "eleven_multilingual_v2",
            default_voice_id: "JBFqnCBsd6RMkjVDRZzb",
            has_default_voice: true,
            storage_mode: "direct_response",
            onedrive_enabled: false,
            onedrive_folder_name: "French Audiobook MP3",
            missing_required: [],
          }),
        { status: 200, headers: { "content-type": "application/json" } },
      ),
    );

    render(<App />);

    expect(screen.getByRole("heading", { name: "French Audiobook" })).toBeInTheDocument();
    expect(screen.getByLabelText("Title")).toBeInTheDocument();
    expect(screen.getByLabelText("French text")).toBeInTheDocument();
    expect(screen.getByLabelText("Voice ID")).toBeInTheDocument();
    expect(screen.getByLabelText("Model ID")).toBeInTheDocument();
    expect(screen.getByLabelText("Pause")).toBeInTheDocument();
    expect(screen.getByRole("slider", { name: "Speed" })).toBeInTheDocument();
    expect(screen.getByRole("slider", { name: "Stability" })).toBeInTheDocument();
    expect(screen.getByRole("slider", { name: "Similarity" })).toBeInTheDocument();
    expect(screen.getByRole("slider", { name: "Style" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /generate mp3/i })).toBeInTheDocument();

    await waitFor(() => {
      expect(screen.getByText("Default voice is ready.")).toBeInTheDocument();
    });
  });

  it("posts form values and displays streamed preview, download, and metadata", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch");
    fetchMock
      .mockResolvedValueOnce(
        new Response(
          JSON.stringify({
            default_model_id: "eleven_multilingual_v2",
            default_voice_id: "JBFqnCBsd6RMkjVDRZzb",
            has_default_voice: true,
            storage_mode: "direct_response",
            onedrive_enabled: false,
            onedrive_folder_name: "French Audiobook MP3",
            missing_required: [],
          }),
          { status: 200, headers: { "content-type": "application/json" } },
        ),
      )
      .mockResolvedValueOnce(
        new Response(new Blob(["mp3"], { type: "audio/mpeg" }), {
          status: 201,
          headers: {
            "content-type": "audio/mpeg",
            "content-disposition": 'attachment; filename="lecon.mp3"',
            "x-audiobook-segments": "2",
            "x-elevenlabs-character-count": "9000",
            "x-elevenlabs-character-limit": "10000",
            "x-elevenlabs-character-remaining": "1000",
            "x-elevenlabs-character-remaining-percent": "10",
          },
        }),
      );

    render(<App />);
    await userEvent.type(screen.getByLabelText("Title"), "Lecon 1");
    await userEvent.type(screen.getByLabelText("French text"), "Bonjour.\n\nComment ca va?");
    await userEvent.clear(screen.getByLabelText("Voice ID"));
    await userEvent.type(screen.getByLabelText("Voice ID"), "voice-2");
    await userEvent.clear(screen.getByLabelText("Pause"));
    await userEvent.type(screen.getByLabelText("Pause"), "750");
    await userEvent.click(screen.getByRole("button", { name: /generate mp3/i }));

    await waitFor(() => {
      expect(fetchMock).toHaveBeenLastCalledWith(
        "/api/generate",
        expect.objectContaining({
          method: "POST",
          headers: { "content-type": "application/json" },
          body: expect.stringContaining('"voice_id":"voice-2"'),
        }),
      );
    });

    expect(await screen.findByText("Generated successfully.")).toBeInTheDocument();
    expect(URL.createObjectURL).toHaveBeenCalledTimes(1);
    expect(screen.getByLabelText("Generated audio preview")).toHaveAttribute("src", "blob:generated-audio");
    expect(screen.getByRole("link", { name: "Download MP3" })).toHaveAttribute("href", "blob:generated-audio");
    expect(screen.getByRole("link", { name: "Download MP3" })).toHaveAttribute("download", "lecon.mp3");
    expect(screen.getByText("1,000 characters remaining")).toBeInTheDocument();
    expect(screen.getByText("9,000 of 10,000 used.")).toBeInTheDocument();
    expect(screen.getByText("lecon.mp3")).toBeInTheDocument();
    expect(screen.getByText("2")).toBeInTheDocument();
  });

  it("warns after generation when ElevenLabs quota is running low", async () => {
    vi.spyOn(globalThis, "fetch")
      .mockResolvedValueOnce(
        new Response(
          JSON.stringify({
            default_model_id: "eleven_multilingual_v2",
            default_voice_id: "JBFqnCBsd6RMkjVDRZzb",
            has_default_voice: true,
            storage_mode: "direct_response",
            onedrive_enabled: false,
            onedrive_folder_name: "French Audiobook MP3",
            missing_required: [],
          }),
          { status: 200, headers: { "content-type": "application/json" } },
        ),
      )
      .mockResolvedValueOnce(
        new Response(new Blob(["mp3"], { type: "audio/mpeg" }), {
          status: 201,
          headers: {
            "content-type": "audio/mpeg",
            "content-disposition": 'attachment; filename="low-quota.mp3"',
            "x-audiobook-segments": "1",
            "x-elevenlabs-character-count": "9800",
            "x-elevenlabs-character-limit": "10000",
            "x-elevenlabs-character-remaining": "200",
            "x-elevenlabs-character-remaining-percent": "2",
          },
        }),
      );

    render(<App />);
    await userEvent.type(screen.getByLabelText("French text"), "Bonjour.");
    await userEvent.click(screen.getByRole("button", { name: /generate mp3/i }));

    expect(await screen.findByText("200 characters remaining")).toBeInTheDocument();
    expect(screen.getByText("Low ElevenLabs quota")).toBeInTheDocument();
    expect(screen.getByText("Top up soon to avoid failed MP3 generation.")).toBeInTheDocument();
  });

  it("fills the configured default voice so generation and download are not blocked", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch");
    fetchMock
      .mockResolvedValueOnce(
        new Response(
          JSON.stringify({
            default_model_id: "eleven_multilingual_v2",
            default_voice_id: "JBFqnCBsd6RMkjVDRZzb",
            has_default_voice: true,
            storage_mode: "direct_response",
            onedrive_enabled: false,
            onedrive_folder_name: "French Audiobook MP3",
            missing_required: [],
          }),
          { status: 200, headers: { "content-type": "application/json" } },
        ),
      )
      .mockResolvedValueOnce(
        new Response(new Blob(["mp3"], { type: "audio/mpeg" }), {
          status: 201,
          headers: {
            "content-type": "audio/mpeg",
            "content-disposition": 'attachment; filename="default-voice.mp3"',
            "x-audiobook-segments": "1",
          },
        }),
      );

    render(<App />);

    await waitFor(() => {
      expect(screen.getByLabelText("Voice ID")).toHaveValue("JBFqnCBsd6RMkjVDRZzb");
    });
    expect(screen.getByLabelText("Voice ID")).not.toBeRequired();
    await userEvent.type(screen.getByLabelText("French text"), "Bonjour.");
    await userEvent.click(screen.getByRole("button", { name: /generate mp3/i }));

    await waitFor(() => {
      expect(fetchMock).toHaveBeenLastCalledWith(
        "/api/generate",
        expect.objectContaining({
          body: expect.stringContaining('"voice_id":"JBFqnCBsd6RMkjVDRZzb"'),
        }),
      );
    });
    expect(await screen.findByRole("link", { name: "Download MP3" })).toHaveAttribute(
      "download",
      "default-voice.mp3",
    );
  });

  it("shows missing local settings and keeps generation disabled", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValueOnce(
      new Response(
          JSON.stringify({
            default_model_id: "eleven_multilingual_v2",
            default_voice_id: "",
            has_default_voice: false,
            output_dir: "",
            storage_mode: "direct_response",
            onedrive_enabled: false,
            onedrive_folder_name: "French Audiobook MP3",
            missing_required: ["ELEVENLABS_API_KEY"],
          }),
        { status: 200, headers: { "content-type": "application/json" } },
      ),
    );

    render(<App />);

    await waitFor(() => {
      expect(
        screen.getByText("Set ELEVENLABS_API_KEY in .env to enable generation."),
      ).toBeInTheDocument();
    });
    expect(screen.getByLabelText("Voice ID")).toBeRequired();
    expect(screen.getByRole("button", { name: /generate mp3/i })).toBeDisabled();
  });

  it("allows generation attempts when only the default voice is missing", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValueOnce(
      new Response(
        JSON.stringify({
          default_model_id: "eleven_multilingual_v2",
          default_voice_id: "",
          has_default_voice: false,
          storage_mode: "direct_response",
          onedrive_enabled: false,
          onedrive_folder_name: "French Audiobook MP3",
          missing_required: [],
        }),
        { status: 200, headers: { "content-type": "application/json" } },
      ),
    );

    render(<App />);

    await waitFor(() => {
      expect(screen.getByText("Enter a Voice ID or set ELEVENLABS_DEFAULT_VOICE_ID.")).toBeInTheDocument();
    });
    expect(screen.getByLabelText("Voice ID")).toBeRequired();
    expect(screen.getByRole("button", { name: /generate mp3/i })).toBeEnabled();
  });

  it("offers Microsoft auth after generation when OneDrive is configured but disconnected", async () => {
    vi.spyOn(globalThis, "fetch")
      .mockResolvedValueOnce(
        new Response(
          JSON.stringify({
            default_model_id: "eleven_multilingual_v2",
            default_voice_id: "JBFqnCBsd6RMkjVDRZzb",
            has_default_voice: true,
            storage_mode: "direct_response",
            onedrive_enabled: true,
            onedrive_folder_name: "French Audiobook MP3",
            missing_required: [],
          }),
          { status: 200, headers: { "content-type": "application/json" } },
        ),
      )
      .mockResolvedValueOnce(
        new Response(JSON.stringify({ enabled: true, connected: false }), {
          status: 200,
          headers: { "content-type": "application/json" },
        }),
      )
      .mockResolvedValueOnce(
        new Response(new Blob(["mp3"], { type: "audio/mpeg" }), {
          status: 201,
          headers: {
            "content-type": "audio/mpeg",
            "content-disposition": 'attachment; filename="onedrive.mp3"',
            "x-audiobook-segments": "1",
          },
        }),
      );

    render(<App />);
    await userEvent.type(screen.getByLabelText("French text"), "Bonjour.");
    await userEvent.click(screen.getByRole("button", { name: /generate mp3/i }));

    expect(await screen.findByRole("link", { name: "Connect OneDrive" })).toHaveAttribute(
      "href",
      "/api/auth/microsoft/start",
    );
  });

  it("saves the already-generated MP3 blob to OneDrive when connected", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch");
    fetchMock
      .mockResolvedValueOnce(
        new Response(
          JSON.stringify({
            default_model_id: "eleven_multilingual_v2",
            default_voice_id: "JBFqnCBsd6RMkjVDRZzb",
            has_default_voice: true,
            storage_mode: "direct_response",
            onedrive_enabled: true,
            onedrive_folder_name: "French Audiobook MP3",
            missing_required: [],
          }),
          { status: 200, headers: { "content-type": "application/json" } },
        ),
      )
      .mockResolvedValueOnce(
        new Response(JSON.stringify({ enabled: true, connected: true }), {
          status: 200,
          headers: { "content-type": "application/json" },
        }),
      )
      .mockResolvedValueOnce(
        new Response(new Blob(["mp3"], { type: "audio/mpeg" }), {
          status: 201,
          headers: {
            "content-type": "audio/mpeg",
            "content-disposition": 'attachment; filename="onedrive.mp3"',
            "x-audiobook-segments": "1",
          },
        }),
      )
      .mockResolvedValueOnce(
        new Response(JSON.stringify({ name: "onedrive.mp3", webViewLink: "https://onedrive/file" }), {
          status: 200,
          headers: { "content-type": "application/json" },
        }),
      );

    render(<App />);
    await userEvent.type(screen.getByLabelText("Title"), "OneDrive");
    await userEvent.type(screen.getByLabelText("French text"), "Bonjour.");
    await userEvent.click(screen.getByRole("button", { name: /generate mp3/i }));
    await userEvent.click(await screen.findByRole("button", { name: "Save to OneDrive" }));

    await waitFor(() => {
      expect(fetchMock).toHaveBeenLastCalledWith(
        "/api/drive/save",
        expect.objectContaining({
          method: "POST",
        }),
      );
    });
    const saveRequest = fetchMock.mock.calls.at(-1)?.[1] as RequestInit;
    expect(saveRequest.headers).toBeUndefined();
    expect(saveRequest.body).toBeInstanceOf(FormData);
    const formData = saveRequest.body as FormData;
    expect(formData.get("filename")).toBe("onedrive.mp3");
    expect(formData.get("audio")).toBeInstanceOf(Blob);
    expect((formData.get("audio") as Blob).type).toBe("audio/mpeg");
    expect(await screen.findByText("Saved to OneDrive: onedrive.mp3")).toBeInTheDocument();
  });

  it("restores a generated MP3 after auth reload and saves it without generating again", async () => {
    const restored: StoredGenerationResult = {
      audio: new Blob(["stored-mp3"], { type: "audio/mpeg" }),
      filename: "restored-onedrive.mp3",
      segments: 1,
      payload: {
        title: "Restored",
        text: "Bonjour.",
        voice_id: "JBFqnCBsd6RMkjVDRZzb",
        model_id: "eleven_multilingual_v2",
        pause_ms: 500,
        speed: 1,
        stability: 0.5,
        similarity_boost: 0.75,
        style: 0,
      },
    };
    vi.mocked(loadStoredGeneration).mockResolvedValueOnce(restored);
    const fetchMock = vi.spyOn(globalThis, "fetch");
    fetchMock
      .mockResolvedValueOnce(
        new Response(
          JSON.stringify({
            default_model_id: "eleven_multilingual_v2",
            default_voice_id: "JBFqnCBsd6RMkjVDRZzb",
            has_default_voice: true,
            storage_mode: "direct_response",
            onedrive_enabled: true,
            onedrive_folder_name: "French Audiobook MP3",
            missing_required: [],
          }),
          { status: 200, headers: { "content-type": "application/json" } },
        ),
      )
      .mockResolvedValueOnce(
        new Response(JSON.stringify({ enabled: true, connected: true }), {
          status: 200,
          headers: { "content-type": "application/json" },
        }),
      )
      .mockResolvedValueOnce(
        new Response(JSON.stringify({ name: "restored-onedrive.mp3" }), {
          status: 200,
          headers: { "content-type": "application/json" },
        }),
      );

    render(<App />);

    expect(await screen.findByText("Restored generated audio.")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Download MP3" })).toHaveAttribute(
      "download",
      "restored-onedrive.mp3",
    );
    await userEvent.click(await screen.findByRole("button", { name: "Save to OneDrive" }));

    await waitFor(() => {
      expect(fetchMock).toHaveBeenLastCalledWith(
        "/api/drive/save",
        expect.objectContaining({ method: "POST" }),
      );
    });
    expect(fetchMock.mock.calls.some(([url]) => url === "/api/generate")).toBe(false);
    expect(await screen.findByText("Saved to OneDrive: restored-onedrive.mp3")).toBeInTheDocument();
  });
});
