import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { NoteImageCarousel } from './NoteImageCarousel';

describe('NoteImageCarousel', () => {
  it('renders single image without navigation controls', () => {
    render(<NoteImageCarousel slides={[{ src: '/img-1.jpg' }]} alt="测试图片" />);
    expect(screen.getByRole('img', { name: '测试图片' })).toHaveAttribute('src', '/img-1.jpg');
    expect(screen.queryByLabelText('下一张')).toBeNull();
    expect(screen.queryByText('1/1')).toBeNull();
  });

  it('shows placeholder after primary and fallback both fail', () => {
    render(
      <NoteImageCarousel
        slides={[{ src: '/broken.jpg', fallbackSrc: '/broken-fallback.jpg' }]}
        alt="失败图片"
      />,
    );
    const image = screen.getByRole('img', { name: '失败图片' });
    fireEvent.error(image);
    expect(screen.getByRole('img', { name: '失败图片' })).toHaveAttribute('src', '/broken-fallback.jpg');
    fireEvent.error(screen.getByRole('img', { name: '失败图片' }));
    expect(screen.getByText('无图')).toBeInTheDocument();
  });

  it('switches slides with next button and shows counter', () => {
    render(
      <NoteImageCarousel
        slides={[{ src: '/img-1.jpg' }, { src: '/img-2.jpg' }]}
        alt="多图笔记"
      />,
    );
    expect(screen.getByText('1/2')).toBeTruthy();
    fireEvent.click(screen.getByLabelText('下一张'));
    expect(screen.getByText('2/2')).toBeTruthy();
    expect(screen.getAllByRole('img', { name: '多图笔记' }).some((img) => img.getAttribute('src') === '/img-2.jpg')).toBe(true);
  });
});
