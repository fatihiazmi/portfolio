const dateTime = new Intl.DateTimeFormat("en-GB", { dateStyle: "medium", timeStyle: "short" });
const dateOnly = new Intl.DateTimeFormat("en-GB", { dateStyle: "medium" });

/** ISO timestamp from the API to local date and time. */
export function when(iso: string): string {
  return dateTime.format(new Date(iso));
}

export function day(iso: string): string {
  return dateOnly.format(new Date(iso));
}
