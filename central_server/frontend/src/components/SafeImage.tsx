import { useState } from 'react';

type Props = {
  src?: string | null;
  alt?: string;
  className?: string;
  placeholderClassName?: string;
  frameClassName?: string;
  label?: string;
};

export function SafeImage({
  src,
  alt = '',
  className,
  placeholderClassName,
  frameClassName,
  label = '无图',
}: Props) {
  const [failed, setFailed] = useState(false);
  const placeholder = (
    <span className={placeholderClassName || className || 'image-placeholder'}>{label}</span>
  );
  if (!src || failed) {
    return frameClassName ? <div className={frameClassName}>{placeholder}</div> : placeholder;
  }
  const image = <img className={className} src={src} alt={alt} onError={() => setFailed(true)} />;
  return frameClassName ? <div className={frameClassName}>{image}</div> : image;
}
