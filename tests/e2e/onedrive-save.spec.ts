import { expect, test } from "@playwright/test";

const configPayload = {
  default_model_id: "eleven_multilingual_v2",
  default_voice_id: "JBFqnCBsd6RMkjVDRZzb",
  has_default_voice: true,
  storage_mode: "direct_response",
  onedrive_enabled: true,
  onedrive_folder_name: "French Audiobook MP3",
  missing_required: [],
};

test("saves a restored MP3 to OneDrive without generating again after reload", async ({ page }) => {
  let generateCalls = 0;
  let saveCalls = 0;
  let saveRequestBody = "";

  await page.route("**/api/config", async (route) => {
    await route.fulfill({ json: configPayload });
  });
  await page.route("**/api/auth/microsoft/status", async (route) => {
    await route.fulfill({ json: { enabled: true, connected: true } });
  });
  await page.route("**/api/generate", async (route) => {
    generateCalls += 1;
    await route.fulfill({
      status: 201,
      contentType: "audio/mpeg",
      headers: {
        "content-disposition": 'attachment; filename="browser-flow.mp3"',
        "x-audiobook-segments": "1",
      },
      body: Buffer.from("mp3-bytes"),
    });
  });
  await page.route("**/api/drive/save", async (route) => {
    saveCalls += 1;
    saveRequestBody = route.request().postData() || "";
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ name: "browser-flow.mp3" }),
    });
  });

  await page.goto("/");
  await page.getByLabel("French text").fill("Bonjour.");
  await page.getByRole("button", { name: "Generate MP3" }).click();

  await expect(page.getByText("Generated successfully.")).toBeVisible();
  await expect(page.getByRole("link", { name: "Download MP3" })).toHaveAttribute(
    "download",
    "browser-flow.mp3",
  );
  await expect
    .poll(() =>
      page.evaluate(async () => {
        const request = indexedDB.open("french-audiobook", 1);
        const db = await new Promise<IDBDatabase>((resolve, reject) => {
          request.onsuccess = () => resolve(request.result);
          request.onerror = () => reject(request.error);
        });
        const transaction = db.transaction("generated-audio", "readonly");
        const getRequest = transaction.objectStore("generated-audio").get("last");
        const record = await new Promise<unknown>((resolve, reject) => {
          getRequest.onsuccess = () => resolve(getRequest.result);
          getRequest.onerror = () => reject(getRequest.error);
        });
        db.close();
        return Boolean(record);
      }),
    )
    .toBe(true);

  await page.reload();

  await expect(page.getByText("Restored generated audio.")).toBeVisible();
  await page.getByRole("button", { name: "Save to OneDrive" }).click();

  await expect(page.getByText("Saved to OneDrive: browser-flow.mp3")).toBeVisible();
  expect(generateCalls).toBe(1);
  expect(saveCalls).toBe(1);
  expect(saveRequestBody).toContain('name="filename"');
  expect(saveRequestBody).toContain("browser-flow.mp3");
  expect(saveRequestBody).toContain('name="audio"; filename="browser-flow.mp3"');
});
