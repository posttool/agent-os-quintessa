import { useState } from "react";
import type { CSSProperties } from "react";
import type { Picture } from "../types";

/** A picture from a tool: the real image when there is one, credited when
 * it came from the web. With no image, or one that fails to load, it is
 * drawn as an illustration: its emoji on a wash of colour that is always the
 * same for the same caption. */
export default function PictureView({ picture, size, showCaption = false }: {
  picture: Picture;
  size: "thumb" | "large";
  showCaption?: boolean;
}) {
  const [failed, setFailed] = useState(false);
  const real = Boolean(picture.url) && !failed;
  return (
    <figure className={`picture ${size} kind-${picture.kind}`}>
      {real ? (
        <img src={picture.url} alt={picture.caption} loading="lazy" referrerPolicy="no-referrer"
          onError={() => setFailed(true)} />
      ) : (
        <div className="illustration" role="img" aria-label={picture.caption} style={wash(picture.caption)}>
          <span className="emoji">{picture.emoji || picture.caption.slice(0, 1).toUpperCase()}</span>
        </div>
      )}
      {showCaption && (
        <figcaption>
          {picture.caption}
          {real && picture.credit && (
            picture.page_url
              ? <a className="credit" href={picture.page_url} target="_blank" rel="noreferrer">{picture.credit}</a>
              : <span className="credit">{picture.credit}</span>
          )}
        </figcaption>
      )}
    </figure>
  );
}

function wash(caption: string): CSSProperties {
  let h = 0;
  for (const c of caption.toLowerCase()) h = (h * 31 + c.charCodeAt(0)) % 360;
  return { background: `linear-gradient(135deg, hsl(${h} 70% 62%), hsl(${(h + 40) % 360} 65% 42%))` };
}
