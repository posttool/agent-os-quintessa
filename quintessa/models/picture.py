from __future__ import annotations

from dataclasses import dataclass, field

from quintessa.clock import new_id
from quintessa.models.picture_kind import PictureKind

# A picture at least this many pixels on its short side is clear enough to
# show large; a picture of unknown size (simulated, or an unsized URL) passes.
GOOD_PICTURE_MIN_SIDE = 320


@dataclass
class Picture:
    """A picture a tool returned (a dish, a product, a place). A simulated
    service has no real image, so its pictures have no `url` and skins draw
    an illustration from the emoji and caption instead."""

    caption: str
    kind: PictureKind = PictureKind.PHOTO
    url: str = ""
    emoji: str = ""
    width: int = 0
    height: int = 0
    source: str = ""  # the tool that returned it
    id: str = field(default_factory=lambda: new_id("pic"))

    @property
    def good(self) -> bool:
        """Worth showing large in a document: a photo, not tiny."""
        if self.kind != PictureKind.PHOTO:
            return False
        sized = self.width > 0 and self.height > 0
        return not sized or min(self.width, self.height) >= GOOD_PICTURE_MIN_SIDE
