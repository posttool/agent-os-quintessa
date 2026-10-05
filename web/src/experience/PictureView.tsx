import type { CSSProperties } from "react";
import type { Picture } from "../types";

/** A picture from a tool. A real one is an image; a simulated service's has
 * no url, so it is drawn as an illustration: its emoji on a wash of colour
 * that is always the same for the same caption. */
export default function PictureView({ picture, size, showCaption = false }: {
  picture: Picture;
  size: "thumb" | "large";
  showCaption?: boolean;
}) {
  return (
    <figure className={`picture ${size} kind-${picture.kind}`}>
      {picture.url ? (
        <img src={picture.url} alt={picture.caption} loading="lazy" />
      ) : (
        <div className="illustration" role="img" aria-label={picture.caption} style={wash(picture.caption)}>
          <span className="emoji">{picture.emoji || picture.caption.slice(0, 1).toUpperCase()}</span>
        </div>
      )}
      {showCaption && <figcaption>{picture.caption}</figcaption>}
    </figure>
  );
}

function wash(caption: string): CSSProperties {
  let h = 0;
  for (const c of caption.toLowerCase()) h = (h * 31 + c.charCodeAt(0)) % 360;
  return { background: `linear-gradient(135deg, hsl(${h} 70% 62%), hsl(${(h + 40) % 360} 65% 42%))` };
}
