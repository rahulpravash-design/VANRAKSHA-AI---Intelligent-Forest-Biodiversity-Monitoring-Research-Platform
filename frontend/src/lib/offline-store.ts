"use client";

/**
 * Tracks connectivity and the queue of observations captured while offline.
 *
 * A field capture must never be lost to a dead connection: `observations/new`
 * queues instead of failing (see its handleSubmit), and this store is what
 * drains the queue automatically on reconnect and what the Topbar indicator
 * reads to show a pending count and a manual "Sync now".
 */

import { create } from "zustand";

import { ApiError } from "./api";
import { observationsApi } from "./endpoints";
import {
  countQueuedObservations,
  enqueueObservation,
  isIndexedDbAvailable,
  listQueuedObservations,
  markQueuedObservationError,
  removeQueuedObservation,
  type QueuedObservation,
} from "./offline-queue";

interface OfflineState {
  supported: boolean;
  isOnline: boolean;
  pendingCount: number;
  items: QueuedObservation[];
  syncing: boolean;
  init: () => void;
  refreshQueue: () => Promise<void>;
  queueObservation: (
    fields: Record<string, string>,
    image: File | null,
    audio: File | null
  ) => Promise<void>;
  syncNow: () => Promise<void>;
  discard: (id: number) => Promise<void>;
}

let listenersAttached = false;

export const useOfflineStore = create<OfflineState>((set, get) => ({
  supported: isIndexedDbAvailable(),
  isOnline: typeof navigator === "undefined" ? true : navigator.onLine,
  pendingCount: 0,
  items: [],
  syncing: false,

  init: () => {
    if (!get().supported || listenersAttached || typeof window === "undefined") return;
    listenersAttached = true;
    void get().refreshQueue();
    window.addEventListener("online", () => {
      set({ isOnline: true });
      void get().syncNow();
    });
    window.addEventListener("offline", () => set({ isOnline: false }));
  },

  refreshQueue: async () => {
    if (!get().supported) return;
    const [count, items] = await Promise.all([
      countQueuedObservations(),
      listQueuedObservations(),
    ]);
    set({ pendingCount: count, items });
  },

  queueObservation: async (fields, image, audio) => {
    await enqueueObservation({
      fields,
      image: image ? { name: image.name, type: image.type, blob: image } : null,
      audio: audio ? { name: audio.name, type: audio.type, blob: audio } : null,
    });
    await get().refreshQueue();
  },

  syncNow: async () => {
    if (!get().supported || get().syncing || !get().isOnline) return;
    set({ syncing: true });
    try {
      const queued = await listQueuedObservations();
      for (const item of queued) {
        try {
          const form = new FormData();
          for (const [key, value] of Object.entries(item.fields)) {
            form.set(key, value);
          }
          if (item.image) {
            form.set("image", new File([item.image.blob], item.image.name, { type: item.image.type }));
          }
          if (item.audio) {
            form.set("audio", new File([item.audio.blob], item.audio.name, { type: item.audio.type }));
          }
          await observationsApi.capture(form);
          await removeQueuedObservation(item.id);
        } catch (err) {
          if (err instanceof ApiError) {
            // The server actually answered and rejected it (e.g. validation) —
            // record why and move on to the next item rather than retrying
            // something that will never succeed on its own.
            await markQueuedObservationError(item.id, err.message);
          } else {
            // A network failure — the connection dropped again mid-sync. Stop
            // here; the rest retry on the next reconnect or manual sync.
            break;
          }
        }
      }
    } finally {
      await get().refreshQueue();
      set({ syncing: false });
    }
  },

  discard: async (id: number) => {
    await removeQueuedObservation(id);
    await get().refreshQueue();
  },
}));
