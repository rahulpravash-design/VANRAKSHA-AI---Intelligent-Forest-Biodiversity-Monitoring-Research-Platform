"use client";

/**
 * IndexedDB-backed queue for observation captures made while offline.
 *
 * Files are stored as Blobs — IndexedDB's structured-clone algorithm handles
 * them natively — so a queued submission survives a reload, not just a tab
 * close, which matters for a field researcher who closes the app between a
 * capture and the next signal bar.
 */

const DB_NAME = "vanraksha-offline";
const DB_VERSION = 1;
const STORE = "pending-observations";

export interface QueuedFile {
  name: string;
  type: string;
  blob: Blob;
}

export interface QueuedObservation {
  id: number;
  fields: Record<string, string>;
  image: QueuedFile | null;
  audio: QueuedFile | null;
  queuedAt: string;
  lastError?: string;
}

export function isIndexedDbAvailable(): boolean {
  return typeof indexedDB !== "undefined";
}

function openDb(): Promise<IDBDatabase> {
  return new Promise((resolve, reject) => {
    const request = indexedDB.open(DB_NAME, DB_VERSION);
    request.onupgradeneeded = () => {
      if (!request.result.objectStoreNames.contains(STORE)) {
        request.result.createObjectStore(STORE, { keyPath: "id", autoIncrement: true });
      }
    };
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error);
  });
}

export async function enqueueObservation(
  entry: Omit<QueuedObservation, "id" | "queuedAt">
): Promise<void> {
  const db = await openDb();
  await new Promise<void>((resolve, reject) => {
    const tx = db.transaction(STORE, "readwrite");
    tx.objectStore(STORE).add({ ...entry, queuedAt: new Date().toISOString() });
    tx.oncomplete = () => {
      db.close();
      resolve();
    };
    tx.onerror = () => reject(tx.error);
  });
}

export async function listQueuedObservations(): Promise<QueuedObservation[]> {
  const db = await openDb();
  return new Promise((resolve, reject) => {
    const tx = db.transaction(STORE, "readonly");
    const request = tx.objectStore(STORE).getAll();
    request.onsuccess = () => {
      const items = (request.result as QueuedObservation[]).sort((a, b) =>
        a.queuedAt.localeCompare(b.queuedAt)
      );
      resolve(items);
    };
    request.onerror = () => reject(request.error);
    tx.oncomplete = () => db.close();
  });
}

export async function countQueuedObservations(): Promise<number> {
  const db = await openDb();
  return new Promise((resolve, reject) => {
    const tx = db.transaction(STORE, "readonly");
    const request = tx.objectStore(STORE).count();
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error);
    tx.oncomplete = () => db.close();
  });
}

export async function removeQueuedObservation(id: number): Promise<void> {
  const db = await openDb();
  await new Promise<void>((resolve, reject) => {
    const tx = db.transaction(STORE, "readwrite");
    tx.objectStore(STORE).delete(id);
    tx.oncomplete = () => {
      db.close();
      resolve();
    };
    tx.onerror = () => reject(tx.error);
  });
}

export async function markQueuedObservationError(id: number, message: string): Promise<void> {
  const db = await openDb();
  await new Promise<void>((resolve, reject) => {
    const tx = db.transaction(STORE, "readwrite");
    const store = tx.objectStore(STORE);
    const getRequest = store.get(id);
    getRequest.onsuccess = () => {
      const record = getRequest.result as QueuedObservation | undefined;
      if (record) {
        record.lastError = message;
        store.put(record);
      }
    };
    tx.oncomplete = () => {
      db.close();
      resolve();
    };
    tx.onerror = () => reject(tx.error);
  });
}
