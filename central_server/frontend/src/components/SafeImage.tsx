import { useState } from 'react';

type Props = {
  src?: string | null;
  alt?: string;
  className?: string;
  placeholderClassName?: string;
  label?: string;
};

export function SafeImage({ src, alt = '', className, placeholderClassName, label = '无图' }: Props) {
  const [failed, setFailed] = useState(false);
  if (!src || failed) {
    return <span className={placeholderClassName || className || 'image-placeholder'}>{label}</span>;
  }
  return <img className={className} src={src} alt={alt} onError={() => setFailed(true)} />;
}
