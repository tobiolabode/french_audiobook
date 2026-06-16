import type { ElevenLabsQuota, GeneratePayload } from "./api";

const DB_NAME = "french-audiobook";
const STORE_NAME = "generated-audio";
const LAST_GENERATION_KEY = "last";

export type StoredGenerationResult = {
  audio: Blob;
  filename: string;
  segments: number;
  quota?: ElevenLabsQuota;
  payload: GeneratePayload;
};

type StoredGenerationRecord = StoredGenerationResult & {
  id: string;
  savedAt: number;
};

export async function storeGeneration(result: StoredGenerationResult): Promise<void> {
  const db = await openDatabase();
  await requestToPromise(
    db
      .transaction(STORE_NAME, "readwrite")
      .objectStore(STORE_NAME)
      .put({
        id: LAST_GENERATION_KEY,
        savedAt: Date.now(),
        ...result,
      } satisfies StoredGenerationRecord),
  );
  db.close();
}

export async function loadStoredGeneration(): Promise<StoredGenerationResult | null> {
  const db = await openDatabase();
  const record = await requestToPromise<StoredGenerationRecord | undefined>(
    db.transaction(STORE_NAME, "readonly").objectStore(STORE_NAME).get(LAST_GENERATION_KEY),
  );
  db.close();

  if (!record?.audio) {
    return null;
  }

  return {
    audio: record.audio,
    filename: record.filename,
    segments: record.segments,
    quota: record.quota,
    payload: record.payload,
  };
}

function openDatabase(): Promise<IDBDatabase> {
  if (typeof indexedDB === "undefined") {
    return Promise.reject(new Error("IndexedDB is not available."));
  }

  return new Promise((resolve, reject) => {
    const request = indexedDB.open(DB_NAME, 1);
    request.onupgradeneeded = () => {
      const db = request.result;
      if (!db.objectStoreNames.contains(STORE_NAME)) {
        db.createObjectStore(STORE_NAME, { keyPath: "id" });
      }
    };
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error || new Error("Unable to open IndexedDB."));
  });
}

function requestToPromise<T>(request: IDBRequest<T>): Promise<T> {
  return new Promise((resolve, reject) => {
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error || new Error("IndexedDB request failed."));
  });
}
