import aurora from "./aurora.css?raw";
import paper from "./paper.css?raw";

/** Device skins. Each is a complete, self-contained stylesheet for the
 * experience markup; add a file and an entry here to create a new one. */
export const SKINS: Record<string, string> = { aurora, paper };
export const DEFAULT_SKIN = "aurora";
