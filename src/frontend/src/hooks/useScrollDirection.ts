import { useState, useEffect, useRef, type RefObject } from 'react';

type ScrollDirection = 'up' | 'down' | null;

/**
 * Erkennt die Scroll-Richtung innerhalb eines Containers.
 * Nutzt die Capture-Phase, um Scroll-Events von beliebigen
 * verschachtelten scrollbaren Elementen aufzufangen.
 */
export function useScrollDirection(
  containerRef: RefObject<HTMLElement | null>,
  threshold = 10,
): ScrollDirection {
  const [direction, setDirection] = useState<ScrollDirection>(null);
  const lastY = useRef(0);
  const ticking = useRef(false);

  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;

    const onScroll = (e: Event) => {
      const target = e.target as HTMLElement;
      if (!target || target === document) return;

      if (ticking.current) return;
      ticking.current = true;

      requestAnimationFrame(() => {
        const currentY = target.scrollTop;
        const delta = currentY - lastY.current;

        if (Math.abs(delta) >= threshold) {
          setDirection(delta > 0 ? 'down' : 'up');
          lastY.current = currentY;
        }

        ticking.current = false;
      });
    };

    container.addEventListener('scroll', onScroll, { capture: true, passive: true });
    return () => container.removeEventListener('scroll', onScroll, { capture: true });
  }, [containerRef, threshold]);

  return direction;
}
