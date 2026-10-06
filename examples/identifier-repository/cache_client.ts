export async function cacheLookup(key: string) {
  const response = await fetch(`/api/entries/${encodeURIComponent(key)}`);
  if (!response.ok) {
    throw new Error(`Request failed: ${response.status}`);
  }
  return response.json();
}
