import { useEffect } from 'react';

type Handlers = {
  enabled: boolean;
  onNext: () => void;
  onPrev: () => void;
  onLeadLibrary: () => void;
  onContentLibrary: () => void;
  onWatchLater: () => void;
  onDiscard: () => void;
  onShowHelp: () => void;
};

function isTypingTarget(target: EventTarget | null): boolean {
  if (!(target instanceof HTMLElement)) return false;
  const tag = target.tagName;
  return tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT' || target.isContentEditable;
}

export function useIntelligenceKeyboard(handlers: Handlers) {
  useEffect(() => {
    if (!handlers.enabled) return;

    function onKeyDown(event: KeyboardEvent) {
      if (isTypingTarget(event.target)) return;
      if (event.metaKey || event.ctrlKey || event.altKey) return;

      const key = event.key.toLowerCase();
      switch (key) {
        case 'j':
          event.preventDefault();
          handlers.onNext();
          break;
        case 'k':
          event.preventDefault();
          handlers.onPrev();
          break;
        case 'h':
          event.preventDefault();
          handlers.onLeadLibrary();
          break;
        case 'l':
          event.preventDefault();
          handlers.onContentLibrary();
          break;
        case 's':
          event.preventDefault();
          handlers.onWatchLater();
          break;
        case 'x':
          event.preventDefault();
          handlers.onDiscard();
          break;
        case '?':
          event.preventDefault();
          handlers.onShowHelp();
          break;
        default:
          break;
      }
    }

    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, [handlers]);
}
