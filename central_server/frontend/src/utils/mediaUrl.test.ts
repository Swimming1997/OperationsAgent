import { describe, expect, it } from 'vitest';
import { coverSrc, noteImageSlides } from './mediaUrl';

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

describe('noteImageSlides', () => {
  it('prefers image_display_urls for carousel slides', () => {
    expect(
      noteImageSlides({
        cover_display_url: '/api/media/cover/content-1?e=1&s=abc',
        image_display_urls: ['/api/media/image/content-1?i=1&e=1&s=a', '/api/media/image/content-1?i=2&e=1&s=b'],
        image_urls: ['https://cdn.example/1.jpg', 'https://cdn.example/2.jpg'],
      }),
    ).toEqual([
      { src: '/api/media/image/content-1?i=1&e=1&s=a', fallbackSrc: 'https://cdn.example/1.jpg' },
      { src: '/api/media/image/content-1?i=2&e=1&s=b', fallbackSrc: 'https://cdn.example/2.jpg' },
    ]);
  });

  it('falls back to cover when image_display_urls is empty', () => {
    expect(
      noteImageSlides({
        cover_display_url: '/api/media/cover/content-1?e=1&s=abc',
        cover_url: 'https://cdn.example/cover.jpg',
      }),
    ).toEqual([{ src: '/api/media/cover/content-1?e=1&s=abc', fallbackSrc: 'https://cdn.example/cover.jpg' }]);
  });
});
