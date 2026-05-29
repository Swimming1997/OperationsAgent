import { describe, expect, it } from 'vitest';
import { coverSrc } from './mediaUrl';

describe('coverSrc', () => {
  it('prefers cover_display_url over legacy cover_url', () => {
    expect(
      coverSrc({
        cover_display_url: '/api/media/cover/content-1?e=1&s=abc',
        cover_url: 'https://cdn.example/cover.jpg',
      }),
    ).toBe('/api/media/cover/content-1?e=1&s=abc');
  });

  it('falls back to cover_url when display url is missing', () => {
    expect(coverSrc({ cover_url: 'https://cdn.example/cover.jpg', cover_display_url: null })).toBe(
      'https://cdn.example/cover.jpg',
    );
  });
});
