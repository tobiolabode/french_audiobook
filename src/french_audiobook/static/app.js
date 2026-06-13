const form = document.querySelector("#generate-form");
const button = document.querySelector("#submit-button");
const statusText = document.querySelector("#status");
const preview = document.querySelector("#preview");
const download = document.querySelector("#download");
const metadata = document.querySelector("#metadata");
const savedPath = document.querySelector("#saved-path");
const segments = document.querySelector("#segments");

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  const data = new FormData(form);
  const payload = Object.fromEntries(data.entries());

  button.disabled = true;
  statusText.textContent = "Generating audio...";
  preview.hidden = true;
  download.hidden = true;
  metadata.hidden = true;

  try {
    const response = await fetch("/api/generate", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(payload),
    });
    const result = await response.json();
    if (!response.ok) {
      throw new Error(result.error || "Generation failed.");
    }

    statusText.textContent = "Generated successfully.";
    preview.src = result.preview_url;
    preview.hidden = false;
    download.href = result.download_url;
    download.textContent = "Download MP3";
    download.hidden = false;
    savedPath.textContent = result.path;
    segments.textContent = result.segments;
    metadata.hidden = false;
  } catch (error) {
    statusText.textContent = error.message;
  } finally {
    button.disabled = false;
  }
});
