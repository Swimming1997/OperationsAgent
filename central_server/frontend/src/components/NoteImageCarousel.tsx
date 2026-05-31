import { ChevronLeft, ChevronRight } from 'lucide-react';
import { useEffect, useRef, useState } from 'react';

export type NoteImageSlide = {
  src: string;
  fallbackSrc?: string | null;
};

type Props = {
  slides: NoteImageSlide[];
  alt?: string;
  className?: string;
  frameClassName?: string;
  placeholderClassName?: string;
};

const SWIPE_THRESHOLD = 48;

export function NoteImageCarousel({
  slides,
  alt = '',
  className = 'detail-cover',
  frameClassName = 'cover-media-frame cover-media-frame-detail',
  placeholderClassName = 'detail-cover-placeholder',
}: Props) {
  const validSlides = slides.filter((slide) => slide.src?.trim());
  const [index, setIndex] = useState(0);
  const [dragOffset, setDragOffset] = useState(0);
  const [dragging, setDragging] = useState(false);
  const [activeSrcByKey, setActiveSrcByKey] = useState<Record<string, string>>({});
  const [exhaustedKeys, setExhaustedKeys] = useState<Record<string, true>>({});
  const trackRef = useRef<HTMLDivElement | null>(null);
  const dragState = useRef<{ startX: number; startY: number; active: boolean; locked: boolean | null }>({
    startX: 0,
    startY: 0,
    active: false,
    locked: null,
  });

  useEffect(() => {
    setIndex(0);
    setDragOffset(0);
    setActiveSrcByKey({});
    setExhaustedKeys({});
  }, [validSlides.map((slide) => slide.src).join('|')]);

  useEffect(() => {
    if (index >= validSlides.length) {
      setIndex(Math.max(validSlides.length - 1, 0));
    }
  }, [index, validSlides.length]);

  const placeholder = (
    <span className={placeholderClassName}>无图</span>
  );

  if (validSlides.length === 0) {
    return (
      <div className={`note-image-carousel ${frameClassName}`} aria-label="笔记图片">
        {placeholder}
      </div>
    );
  }

  const showNav = validSlides.length > 1;
  const clampedIndex = Math.min(index, validSlides.length - 1);

  const goTo = (nextIndex: number) => {
    if (!showNav) return;
    setIndex(Math.max(0, Math.min(validSlides.length - 1, nextIndex)));
    setDragOffset(0);
  };

  const finishDrag = (deltaX: number) => {
    if (!showNav) {
      setDragOffset(0);
      return;
    }
    if (deltaX <= -SWIPE_THRESHOLD) {
      goTo(clampedIndex + 1);
      return;
    }
    if (deltaX >= SWIPE_THRESHOLD) {
      goTo(clampedIndex - 1);
      return;
    }
    setDragOffset(0);
  };

  const onPointerDown = (event: React.PointerEvent<HTMLDivElement>) => {
    if (!showNav) return;
    dragState.current = {
      startX: event.clientX,
      startY: event.clientY,
      active: true,
      locked: null,
    };
    setDragging(true);
    event.currentTarget.setPointerCapture(event.pointerId);
  };

  const onPointerMove = (event: React.PointerEvent<HTMLDivElement>) => {
    const state = dragState.current;
    if (!state.active || !showNav) return;

    const deltaX = event.clientX - state.startX;
    const deltaY = event.clientY - state.startY;

    if (state.locked === null) {
      if (Math.abs(deltaX) < 8 && Math.abs(deltaY) < 8) return;
      state.locked = Math.abs(deltaX) > Math.abs(deltaY);
    }
    if (!state.locked) return;

    event.preventDefault();
    let offset = deltaX;
    if ((clampedIndex === 0 && offset > 0) || (clampedIndex === validSlides.length - 1 && offset < 0)) {
      offset *= 0.35;
    }
    setDragOffset(offset);
  };

  const onPointerUp = (event: React.PointerEvent<HTMLDivElement>) => {
    const state = dragState.current;
    if (!state.active) return;
    const deltaX = event.clientX - state.startX;
    state.active = false;
    state.locked = null;
    setDragging(false);
    if (event.currentTarget.hasPointerCapture(event.pointerId)) {
      event.currentTarget.releasePointerCapture(event.pointerId);
    }
    finishDrag(deltaX);
  };

  const onPointerCancel = () => {
    dragState.current.active = false;
    dragState.current.locked = null;
    setDragging(false);
    setDragOffset(0);
  };

  const translateX = `calc(${-clampedIndex * 100}% + ${dragOffset}px)`;

  return (
    <div className={`note-image-carousel ${frameClassName}`} aria-label="笔记图片">
      <div
        ref={trackRef}
        className={`note-image-carousel-track${dragging ? ' is-dragging' : ''}`}
        style={{ transform: `translate3d(${translateX}, 0, 0)` }}
        onPointerDown={onPointerDown}
        onPointerMove={onPointerMove}
        onPointerUp={onPointerUp}
        onPointerCancel={onPointerCancel}
      >
        {validSlides.map((slide, slideIndex) => {
          const slideKey = `${slide.src}:${slide.fallbackSrc || ''}`;
          const activeSrc = activeSrcByKey[slideKey] ?? slide.src;
          return (
            <div key={`${slide.src}-${slideIndex}`} className="note-image-carousel-slide">
              {!activeSrc || exhaustedKeys[slideKey] ? (
                placeholder
              ) : (
                <img
                  className={className}
                  src={activeSrc}
                  alt={alt}
                  draggable={false}
                  onError={() => {
                    if (slide.fallbackSrc && activeSrc !== slide.fallbackSrc) {
                      setActiveSrcByKey((current) => ({ ...current, [slideKey]: slide.fallbackSrc! }));
                      return;
                    }
                    setExhaustedKeys((current) => ({ ...current, [slideKey]: true }));
                  }}
                />
              )}
            </div>
          );
        })}
      </div>

      {showNav ? (
        <>
          <button
            type="button"
            className="note-image-carousel-nav note-image-carousel-nav-prev"
            aria-label="上一张"
            disabled={clampedIndex === 0}
            onClick={() => goTo(clampedIndex - 1)}
          >
            <ChevronLeft size={18} />
          </button>
          <button
            type="button"
            className="note-image-carousel-nav note-image-carousel-nav-next"
            aria-label="下一张"
            disabled={clampedIndex === validSlides.length - 1}
            onClick={() => goTo(clampedIndex + 1)}
          >
            <ChevronRight size={18} />
          </button>
          <div className="note-image-carousel-dots" aria-hidden="true">
            {validSlides.map((slide, dotIndex) => (
              <button
                key={`dot-${slide.src}-${dotIndex}`}
                type="button"
                className={`note-image-carousel-dot${dotIndex === clampedIndex ? ' is-active' : ''}`}
                aria-label={`第 ${dotIndex + 1} 张`}
                onClick={() => goTo(dotIndex)}
              />
            ))}
          </div>
          <div className="note-image-carousel-counter" aria-live="polite">
            {clampedIndex + 1}/{validSlides.length}
          </div>
        </>
      ) : null}
    </div>
  );
}
