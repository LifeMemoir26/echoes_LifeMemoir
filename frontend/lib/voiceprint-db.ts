/**
 * Voiceprint IndexedDB storage — saves/loads PCM audio chunks keyed by username.
 *
 * Each recording is ~5s of 16 kHz mono Int16 PCM → ~125 chunks × 1280 bytes ≈ 160 KB.
 * IndexedDB handles this comfortably and persists across page refreshes.
 */

const DB_NAME = "echoes_voiceprint";
const DB_VERSION = 1;
const STORE_NAME = "recordings";

function openDb(): Promise<IDBDatabase> {
  return new Promise((resolve, reject) => {
    const req = indexedDB.open(DB_NAME, DB_VERSION);
    req.onupgradeneeded = () => {
      const db = req.result;
      if (!db.objectStoreNames.contains(STORE_NAME)) {
        db.createObjectStore(STORE_NAME);
      }
    };
    req.onsuccess = () => resolve(req.result);
    req.onerror = () => reject(req.error);
  });
}

/** Persist voiceprint PCM chunks for a given username. */
export async function saveVoiceprint(
  username: string,
  chunks: ArrayBuffer[],
): Promise<void> {
  const db = await openDb();
  return new Promise((resolve, reject) => {
    const tx = db.transaction(STORE_NAME, "readwrite");
    tx.objectStore(STORE_NAME).put(chunks, username);
    tx.oncomplete = () => {
      db.close();
      resolve();
    };
    tx.onerror = () => {
      db.close();
      reject(tx.error);
    };
  });
}

/** Load previously saved voiceprint chunks. Returns null if none exist. */
export async function loadVoiceprint(
  username: string,
): Promise<ArrayBuffer[] | null> {
  const db = await openDb();
  return new Promise((resolve, reject) => {
    const tx = db.transaction(STORE_NAME, "readonly");
    const req = tx.objectStore(STORE_NAME).get(username);
    req.onsuccess = () => {
      db.close();
      resolve((req.result as ArrayBuffer[] | undefined) ?? null);
    };
    req.onerror = () => {
      db.close();
      reject(req.error);
    };
  });
}

/** Delete a stored voiceprint. */
export async function deleteVoiceprint(username: string): Promise<void> {
  const db = await openDb();
  return new Promise((resolve, reject) => {
    const tx = db.transaction(STORE_NAME, "readwrite");
    tx.objectStore(STORE_NAME).delete(username);
    tx.oncomplete = () => {
      db.close();
      resolve();
    };
    tx.onerror = () => {
      db.close();
      reject(tx.error);
    };
  });
}

/** Check whether a voiceprint exists for the username (without loading data). */
export async function hasVoiceprint(username: string): Promise<boolean> {
  const db = await openDb();
  return new Promise((resolve, reject) => {
    const tx = db.transaction(STORE_NAME, "readonly");
    const req = tx.objectStore(STORE_NAME).count(
      IDBKeyRange.only(username),
    );
    req.onsuccess = () => {
      db.close();
      resolve(req.result > 0);
    };
    req.onerror = () => {
      db.close();
      reject(req.error);
    };
  });
}
