import { useEffect, useState } from 'react';

type Props = {
  src?: string | null;
  fallbackSrc?: string | null;
  alt?: string;
  className?: string;
  placeholderClassName?: string;
  frameClassName?: string;
  label?: string;
};

export function SafeImage({
  src,
  fallbackSrc,
  alt = '',
  className,
  placeholderClassName,
  frameClassName,
  label = '无图',
}: Props) {
  const [activeSrc, setActiveSrc] = useState<string | null | undefined>(src);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    setActiveSrc(src);
    setFailed(false);
  }, [src, fallbackSrc]);

  const placeholder = (
    <span className={placeholderClassName || className || 'image-placeholder'}>{label}</span>
  );
  if (!activeSrc || failed) {
    return frameClassName ? <div className={frameClassName}>{placeholder}</div> : placeholder;
  }
  const image = (
    <img
      className={className}
      src={activeSrc}
      alt={alt}
      onError={() => {
        if (fallbackSrc && activeSrc !== fallbackSrc) {
          setActiveSrc(fallbackSrc);
          return;
        }
        setFailed(true);
      }}
    />
  );
  return frameClassName ? <div className={frameClassName}>{image}</div> : image;
}
