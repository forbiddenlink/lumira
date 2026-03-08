"""Social media posting with actual API integration.

Supports:
- Twitter/X (via tweepy)
- Instagram (via instagrapi)
- Bluesky (via atproto)

Requires API credentials in environment variables or config.
"""

import io
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from PIL import Image
from pydantic import BaseModel, Field

from ..utils.logging import get_logger

logger = get_logger(__name__)

# Check for API library availability
TWITTER_AVAILABLE = False
INSTAGRAM_AVAILABLE = False
BLUESKY_AVAILABLE = False

try:
    import tweepy

    TWITTER_AVAILABLE = True
except ImportError:
    pass

try:
    from instagrapi import Client as InstaClient

    INSTAGRAM_AVAILABLE = True
except ImportError:
    pass

try:
    from atproto import Client as BlueskyClient

    BLUESKY_AVAILABLE = True
except ImportError:
    pass


class PostResult(BaseModel):
    """Result of a social media post."""

    platform: str
    success: bool
    post_id: str | None = None
    post_url: str | None = None
    error: str | None = None
    posted_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class TwitterPoster:
    """Twitter/X API poster using tweepy."""

    def __init__(
        self,
        api_key: str | None = None,
        api_secret: str | None = None,
        access_token: str | None = None,
        access_secret: str | None = None,
        bearer_token: str | None = None,
    ):
        """Initialize Twitter poster.

        Args:
            api_key: Twitter API key (or TWITTER_API_KEY env var)
            api_secret: Twitter API secret (or TWITTER_API_SECRET env var)
            access_token: Twitter access token (or TWITTER_ACCESS_TOKEN env var)
            access_secret: Twitter access secret (or TWITTER_ACCESS_SECRET env var)
            bearer_token: Twitter bearer token (or TWITTER_BEARER_TOKEN env var)
        """
        if not TWITTER_AVAILABLE:
            logger.warning("twitter_unavailable", reason="tweepy not installed")
            self._client = None
            self._api = None
            return

        self.api_key = api_key or os.getenv("TWITTER_API_KEY")
        self.api_secret = api_secret or os.getenv("TWITTER_API_SECRET")
        self.access_token = access_token or os.getenv("TWITTER_ACCESS_TOKEN")
        self.access_secret = access_secret or os.getenv("TWITTER_ACCESS_SECRET")
        self.bearer_token = bearer_token or os.getenv("TWITTER_BEARER_TOKEN")

        self._client = None
        self._api = None

        if all([self.api_key, self.api_secret, self.access_token, self.access_secret]):
            try:
                # v2 client for tweets
                self._client = tweepy.Client(
                    consumer_key=self.api_key,
                    consumer_secret=self.api_secret,
                    access_token=self.access_token,
                    access_token_secret=self.access_secret,
                )
                # v1.1 API for media uploads
                auth = tweepy.OAuth1UserHandler(
                    self.api_key,
                    self.api_secret,
                    self.access_token,
                    self.access_secret,
                )
                self._api = tweepy.API(auth)
                logger.info("twitter_poster_initialized")
            except Exception as e:
                logger.error("twitter_init_failed", error=str(e))
        else:
            logger.warning("twitter_credentials_missing")

    @property
    def is_available(self) -> bool:
        """Check if Twitter posting is available."""
        return self._client is not None and self._api is not None

    def post(
        self,
        image: Image.Image | Path,
        text: str,
        alt_text: str | None = None,
    ) -> PostResult:
        """Post image with text to Twitter.

        Args:
            image: PIL Image or path to image file
            text: Tweet text (max 280 chars)
            alt_text: Alt text for accessibility

        Returns:
            PostResult with success/failure info
        """
        if not self.is_available:
            return PostResult(
                platform="twitter",
                success=False,
                error="Twitter API not configured",
            )

        try:
            # Prepare image
            if isinstance(image, Path):
                image = Image.open(image)

            # Save to bytes buffer
            buffer = io.BytesIO()
            image.save(buffer, format="PNG")
            buffer.seek(0)

            # Upload media using v1.1 API
            media = self._api.media_upload(filename="lumira_art.png", file=buffer)

            # Add alt text if provided
            if alt_text:
                self._api.create_media_metadata(media.media_id, alt_text=alt_text[:1000])

            # Post tweet using v2 API
            response = self._client.create_tweet(text=text[:280], media_ids=[media.media_id])

            tweet_id = response.data["id"]
            # Get username for URL
            me = self._client.get_me()
            username = me.data.username if me.data else "lumira"
            post_url = f"https://twitter.com/{username}/status/{tweet_id}"

            logger.info("twitter_post_success", tweet_id=tweet_id)

            return PostResult(
                platform="twitter",
                success=True,
                post_id=tweet_id,
                post_url=post_url,
            )

        except Exception as e:
            logger.error("twitter_post_failed", error=str(e))
            return PostResult(
                platform="twitter",
                success=False,
                error=str(e),
            )


class InstagramPoster:
    """Instagram API poster using instagrapi."""

    def __init__(
        self,
        username: str | None = None,
        password: str | None = None,
        session_file: str | None = None,
    ):
        """Initialize Instagram poster.

        Args:
            username: Instagram username (or INSTAGRAM_USERNAME env var)
            password: Instagram password (or INSTAGRAM_PASSWORD env var)
            session_file: Path to session file for persistent login
        """
        if not INSTAGRAM_AVAILABLE:
            logger.warning("instagram_unavailable", reason="instagrapi not installed")
            self._client = None
            return

        self.username = username or os.getenv("INSTAGRAM_USERNAME")
        self.password = password or os.getenv("INSTAGRAM_PASSWORD")
        self.session_file = session_file or os.getenv(
            "INSTAGRAM_SESSION_FILE", "data/instagram_session.json"
        )

        self._client = None

        if self.username and self.password:
            try:
                self._client = InstaClient()

                # Try to load existing session
                if Path(self.session_file).exists():
                    try:
                        self._client.load_settings(self.session_file)
                        self._client.login(self.username, self.password)
                        logger.info("instagram_session_restored")
                    except Exception:
                        # Session expired, do fresh login
                        self._client.login(self.username, self.password)
                        self._client.dump_settings(self.session_file)
                        logger.info("instagram_fresh_login")
                else:
                    self._client.login(self.username, self.password)
                    Path(self.session_file).parent.mkdir(parents=True, exist_ok=True)
                    self._client.dump_settings(self.session_file)
                    logger.info("instagram_poster_initialized")

            except Exception as e:
                logger.error("instagram_init_failed", error=str(e))
                self._client = None
        else:
            logger.warning("instagram_credentials_missing")

    @property
    def is_available(self) -> bool:
        """Check if Instagram posting is available."""
        return self._client is not None

    def post(
        self,
        image: Image.Image | Path,
        caption: str,
        hashtags: list[str] | None = None,
    ) -> PostResult:
        """Post image with caption to Instagram.

        Args:
            image: PIL Image or path to image file
            caption: Post caption (max 2200 chars)
            hashtags: Optional hashtags to append

        Returns:
            PostResult with success/failure info
        """
        if not self.is_available:
            return PostResult(
                platform="instagram",
                success=False,
                error="Instagram API not configured",
            )

        try:
            # Prepare image
            if isinstance(image, Image.Image):
                # Save to temp file (instagrapi requires file path)
                import tempfile

                with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as f:
                    # Convert to RGB and save as JPEG
                    image.convert("RGB").save(f, format="JPEG", quality=95)
                    image_path = f.name
            else:
                image_path = str(image)

            # Build caption with hashtags
            full_caption = caption[:2000]
            if hashtags:
                hashtag_str = " ".join(f"#{h}" for h in hashtags[:30])
                if len(full_caption) + len(hashtag_str) + 2 <= 2200:
                    full_caption = f"{full_caption}\n\n{hashtag_str}"

            # Upload photo
            media = self._client.photo_upload(image_path, full_caption)

            post_url = f"https://www.instagram.com/p/{media.code}/"

            logger.info("instagram_post_success", media_id=media.pk)

            return PostResult(
                platform="instagram",
                success=True,
                post_id=media.pk,
                post_url=post_url,
            )

        except Exception as e:
            logger.error("instagram_post_failed", error=str(e))
            return PostResult(
                platform="instagram",
                success=False,
                error=str(e),
            )


class BlueskyPoster:
    """Bluesky/AT Protocol poster."""

    def __init__(
        self,
        handle: str | None = None,
        password: str | None = None,
    ):
        """Initialize Bluesky poster.

        Args:
            handle: Bluesky handle (or BLUESKY_HANDLE env var)
            password: Bluesky app password (or BLUESKY_PASSWORD env var)
        """
        if not BLUESKY_AVAILABLE:
            logger.warning("bluesky_unavailable", reason="atproto not installed")
            self._client = None
            return

        self.handle = handle or os.getenv("BLUESKY_HANDLE")
        self.password = password or os.getenv("BLUESKY_PASSWORD")

        self._client = None

        if self.handle and self.password:
            try:
                self._client = BlueskyClient()
                self._client.login(self.handle, self.password)
                logger.info("bluesky_poster_initialized")
            except Exception as e:
                logger.error("bluesky_init_failed", error=str(e))
                self._client = None
        else:
            logger.warning("bluesky_credentials_missing")

    @property
    def is_available(self) -> bool:
        """Check if Bluesky posting is available."""
        return self._client is not None

    def post(
        self,
        image: Image.Image | Path,
        text: str,
        alt_text: str | None = None,
    ) -> PostResult:
        """Post image with text to Bluesky.

        Args:
            image: PIL Image or path to image file
            text: Post text (max 300 chars)
            alt_text: Alt text for image

        Returns:
            PostResult with success/failure info
        """
        if not self.is_available:
            return PostResult(
                platform="bluesky",
                success=False,
                error="Bluesky API not configured",
            )

        try:
            # Prepare image
            if isinstance(image, Path):
                image = Image.open(image)

            # Save to bytes
            buffer = io.BytesIO()
            image.save(buffer, format="PNG")
            image_bytes = buffer.getvalue()

            # Upload image
            upload = self._client.upload_blob(image_bytes)

            # Create post with image embed
            self._client.send_image(
                text=text[:300],
                image=image_bytes,
                image_alt=alt_text or "AI-generated artwork by Lumira",
            )

            logger.info("bluesky_post_success")

            return PostResult(
                platform="bluesky",
                success=True,
                post_id="",  # Bluesky doesn't return post ID easily
                post_url=f"https://bsky.app/profile/{self.handle}",
            )

        except Exception as e:
            logger.error("bluesky_post_failed", error=str(e))
            return PostResult(
                platform="bluesky",
                success=False,
                error=str(e),
            )


class SocialPoster:
    """Unified social media poster for multiple platforms."""

    def __init__(self):
        """Initialize all available social posters."""
        self.twitter = TwitterPoster()
        self.instagram = InstagramPoster()
        self.bluesky = BlueskyPoster()

        available = []
        if self.twitter.is_available:
            available.append("twitter")
        if self.instagram.is_available:
            available.append("instagram")
        if self.bluesky.is_available:
            available.append("bluesky")

        logger.info("social_poster_initialized", available_platforms=available)

    def get_available_platforms(self) -> list[str]:
        """Get list of configured platforms."""
        platforms = []
        if self.twitter.is_available:
            platforms.append("twitter")
        if self.instagram.is_available:
            platforms.append("instagram")
        if self.bluesky.is_available:
            platforms.append("bluesky")
        return platforms

    def post_to_all(
        self,
        image: Image.Image | Path,
        text: str,
        hashtags: list[str] | None = None,
        alt_text: str | None = None,
    ) -> dict[str, PostResult]:
        """Post to all available platforms.

        Args:
            image: Image to post
            text: Post text
            hashtags: Hashtags (primarily for Instagram)
            alt_text: Alt text for accessibility

        Returns:
            Dict of platform -> PostResult
        """
        results = {}

        if self.twitter.is_available:
            results["twitter"] = self.twitter.post(image, text, alt_text)

        if self.instagram.is_available:
            results["instagram"] = self.instagram.post(image, text, hashtags)

        if self.bluesky.is_available:
            results["bluesky"] = self.bluesky.post(image, text, alt_text)

        return results

    def post_artwork(
        self,
        image: Image.Image | Path,
        title: str,
        mood: str | None = None,
        style: str | None = None,
        platforms: list[str] | None = None,
    ) -> dict[str, PostResult]:
        """Post artwork with auto-generated caption.

        Args:
            image: Artwork image
            title: Artwork title
            mood: Lumira's mood during creation
            style: Artistic style
            platforms: Specific platforms to post to (or all if None)

        Returns:
            Dict of platform -> PostResult
        """
        # Generate caption
        caption = f'"{title}"'
        if mood:
            caption += f" - created while feeling {mood}"
        caption += "\n\n🎨 AI-generated artwork by Lumira"

        # Hashtags for Instagram
        hashtags = ["AIArt", "GenerativeArt", "Lumira", "AIArtist", "DigitalArt"]
        if style:
            hashtags.append(style.replace(" ", ""))
        if mood:
            hashtags.append(mood.replace(" ", ""))

        # Alt text
        alt_text = f"AI-generated artwork titled '{title}'"
        if style:
            alt_text += f" in {style} style"

        results = {}
        target_platforms = platforms or self.get_available_platforms()

        if "twitter" in target_platforms and self.twitter.is_available:
            twitter_text = f'"{title}" 🎨\n\nAI-generated by Lumira #AIArt #GenerativeArt'
            results["twitter"] = self.twitter.post(image, twitter_text, alt_text)

        if "instagram" in target_platforms and self.instagram.is_available:
            results["instagram"] = self.instagram.post(image, caption, hashtags)

        if "bluesky" in target_platforms and self.bluesky.is_available:
            bsky_text = f'"{title}" 🎨 AI-generated artwork by Lumira'
            results["bluesky"] = self.bluesky.post(image, bsky_text, alt_text)

        return results


# Singleton instance
_poster: SocialPoster | None = None


def get_social_poster() -> SocialPoster:
    """Get or create social poster instance."""
    global _poster
    if _poster is None:
        _poster = SocialPoster()
    return _poster
