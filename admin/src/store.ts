// State the shell and several views share: the dashboard numbers and the admin email.
import { ref } from "vue";
import { api } from "./api";
import type { Summary } from "./types";

export const summary = ref<Summary | null>(null);
export const adminEmail = ref<string | null>(null);

/** Refetch the dashboard numbers. Errors are left to the caller's own requests. */
export async function refreshSummary(): Promise<void> {
  try {
    summary.value = await api.summary();
  } catch {
    // The nav badge and dashboard keep the last numbers.
  }
}

export async function loadMe(): Promise<void> {
  try {
    adminEmail.value = (await api.me()).email;
  } catch {
    adminEmail.value = null;
  }
}
