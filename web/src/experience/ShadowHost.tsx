import { useLayoutEffect, useRef, useState, type ReactNode } from "react";
import { createPortal } from "react-dom";

/** Renders children inside a shadow root with only the skin's stylesheet, so
 * the device experience is isolated from the harness styles and the skin can
 * be swapped without touching either side. */
export default function ShadowHost({ css, theme, children }: { css: string; theme: string; children: ReactNode }) {
  const host = useRef<HTMLDivElement>(null);
  const [root, setRoot] = useState<ShadowRoot | null>(null);

  useLayoutEffect(() => {
    const el = host.current;
    if (el) setRoot(el.shadowRoot ?? el.attachShadow({ mode: "open" }));
  }, []);

  return (
    <div ref={host}>
      {root &&
        createPortal(
          <>
            <style>{css}</style>
            <div className="skin" data-theme={theme}>
              {children}
            </div>
          </>,
          root as unknown as Element,
        )}
    </div>
  );
}
