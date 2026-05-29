type CoverSource = {
  cover_display_url?: string | null;
  cover_url?: string | null;
} | null | undefined;

export function coverSrc(item: CoverSource): string | null {
  if (!item) return null;
  const display = item.cover_display_url?.trim();
  if (display) return display;
  const legacy = item.cover_url?.trim();
  return legacy || null;
}
