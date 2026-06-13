import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { App } from "../../src/app/App";

describe("App", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it("shows the audiobook generation workflow on the first screen", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValueOnce(
      new Response(
        JSON.stringify({
          default_model_id: "eleven_multilingual_v2",
          has_default_voice: true,
          output_dir: "C:/Users/Tobi/OneDrive/French",
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
    expect(screen.getByLabelText("Speed")).toBeInTheDocument();
    expect(screen.getByLabelText("Stability")).toBeInTheDocument();
    expect(screen.getByLabelText("Similarity")).toBeInTheDocument();
    expect(screen.getByLabelText("Style")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /generate mp3/i })).toBeInTheDocument();

    await waitFor(() => {
      expect(screen.getByText("Saving to C:/Users/Tobi/OneDrive/French")).toBeInTheDocument();
    });
  });

  it("posts form values and displays preview, download, and metadata", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch");
    fetchMock
      .mockResolvedValueOnce(
        new Response(
          JSON.stringify({
            default_model_id: "eleven_multilingual_v2",
            has_default_voice: true,
            output_dir: "C:/Audio",
          }),
          { status: 200, headers: { "content-type": "application/json" } },
        ),
      )
      .mockResolvedValueOnce(
        new Response(
          JSON.stringify({
            path: "C:/Audio/lecon.mp3",
            download_url: "/downloads/lecon.mp3",
            preview_url: "/downloads/lecon.mp3",
            segments: 2,
          }),
          { status: 201, headers: { "content-type": "application/json" } },
        ),
      );

    render(<App />);
    await userEvent.type(screen.getByLabelText("Title"), "Lecon 1");
    await userEvent.type(screen.getByLabelText("French text"), "Bonjour.\n\nComment ca va?");
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
    expect(screen.getByLabelText("Generated audio preview")).toHaveAttribute("src", "/downloads/lecon.mp3");
    expect(screen.getByRole("link", { name: "Download MP3" })).toHaveAttribute("href", "/downloads/lecon.mp3");
    expect(screen.getByText("C:/Audio/lecon.mp3")).toBeInTheDocument();
    expect(screen.getByText("2")).toBeInTheDocument();
  });
});
