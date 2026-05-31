type CoverSource = {
  cover_display_url?: string | null;
  cover_url?: string | null;
  image_display_urls?: string[] | null;
  image_urls?: string[] | null;
} | null | undefined;

export type NoteImageSlide = {
  src: string;
  fallbackSrc?: string | null;
};

export function coverSrc(item: CoverSource): string | null {
  if (!item) return null;
  const display = item.cover_display_url?.trim();
  if (display) return display;
  const legacy = item.cover_url?.trim();
  return legacy || null;
}

export function coverFallbackSrc(item: CoverSource): string | null {
  if (!item) return null;
  const display = item.cover_display_url?.trim();
  const legacy = item.cover_url?.trim();
  if (display && legacy && display !== legacy) return legacy;
  return null;
}

export function noteImageSlides(item: CoverSource): NoteImageSlide[] {
  if (!item) return [];

  const displayUrls = (item.image_display_urls || []).map((url) => url?.trim()).filter(Boolean) as string[];
  const rawUrls = (item.image_urls || []).map((url) => url?.trim()).filter(Boolean) as string[];

  if (displayUrls.length > 0) {
    return displayUrls.map((src, index) => ({
      src,
      fallbackSrc: rawUrls[index] && rawUrls[index] !== src ? rawUrls[index] : null,
    }));
  }

  const cover = coverSrc(item);
  if (!cover) return [];
  return [{ src: cover, fallbackSrc: coverFallbackSrc(item) }];
}
