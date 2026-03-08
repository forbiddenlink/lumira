"""Social media integration for AI Artist."""

from .posting import (
    BlueskyPoster,
    InstagramPoster,
    PostResult,
    SocialPoster,
    TwitterPoster,
    get_social_poster,
)
from .sharing import SocialSharing, get_social_sharing

__all__ = [
    # Sharing (preparation)
    "SocialSharing",
    "get_social_sharing",
    # Posting (API integration)
    "BlueskyPoster",
    "InstagramPoster",
    "PostResult",
    "SocialPoster",
    "TwitterPoster",
    "get_social_poster",
]
