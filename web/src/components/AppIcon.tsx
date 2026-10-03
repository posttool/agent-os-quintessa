import { useState } from "react";
import type { AppListing } from "../types";

function hue(text: string): number {
  let h = 0;
  for (const c of text) h = (h * 31 + c.charCodeAt(0)) % 360;
  return h;
}

/** A store icon when the listing has one that loads, else a colored letter tile. */
export default function AppIcon({ listing, name, size = 54, glyph }: {
  listing?: AppListing | null; name: string; size?: number; glyph?: string;
}) {
  const [broken, setBroken] = useState(false);
  const title = listing?.title ?? name;
  const style = { width: size, height: size, borderRadius: size * 0.3, flex: "none", display: "grid", placeItems: "center" };
  if (listing?.icon_url && !broken) {
    return <img className="icon app-icon" src={listing.icon_url} alt="" style={style} onError={() => setBroken(true)} />;
  }
  if (glyph) return <div className="icon" style={style}>{glyph}</div>;
  const tint = listing ? { background: `hsl(${hue(listing.app_id)} 55% 48%)`, color: "#fff", borderColor: "transparent" } : {};
  return <div className="icon" style={{ ...style, fontSize: size * 0.38, ...tint }}>{title[0].toUpperCase()}</div>;
}
