from enum import Enum


class PictureKind(str, Enum):
    """What a picture from a tool shows. Only photos are big and clear enough
    to show in a document once the user picks the thing they show."""

    PHOTO = "photo"
    THUMBNAIL = "thumbnail"
    LOGO = "logo"
    DIAGRAM = "diagram"
