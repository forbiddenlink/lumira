"""Social media sharing functionality."""

from typing import Any

from PIL import Image

from ..utils.logging import get_logger

logger = get_logger(__name__)


class SocialSharing:
    """Social media sharing utilities."""

    def __init__(self) -> None:
        """Initialize social sharing."""
        self.platforms = ["twitter", "instagram", "facebook", "pinterest"]

    async def prepare_for_twitter(
        self,
        image: Image.Image,
        text: str,
        max_chars: int = 280,
    ) -> dict[str, Any]:
        """Prepare image and text for Twitter.

        Args:
            image: PIL Image to share
            text: Tweet text
            max_chars: Maximum characters for tweet

        Returns:
            Dict with prepared data
        """
        try:
            # Twitter image requirements:
            # - Max 5MB for photos
            # - Recommended: 1200x675 (16:9)
            # - Supports: PNG, JPEG, GIF, WebP

            # Resize to Twitter's recommended size if needed
            target_size = (1200, 675)
            if image.size != target_size:
                image = image.resize(target_size, Image.Resampling.LANCZOS)

            # Truncate text if needed
            if len(text) > max_chars:
                text = text[: max_chars - 3] + "..."

            # Add hashtags
            hashtags = ["#AIArt", "#GenerativeArt", "#AIArtist", "#Lumira"]
            text_with_tags = f"{text} {' '.join(hashtags)}"

            if len(text_with_tags) > max_chars:
                # Remove hashtags one by one if needed
                text_with_tags = text

            return {
                "platform": "twitter",
                "image": image,
                "text": text_with_tags,
                "size": image.size,
                "format": "PNG",
            }

        except Exception as e:
            logger.error("twitter_prep_error", error=str(e))
            raise

    async def prepare_for_instagram(
        self,
        image: Image.Image,
        caption: str,
        max_caption: int = 2200,
    ) -> dict[str, Any]:
        """Prepare image and caption for Instagram.

        Args:
            image: PIL Image to share
            caption: Instagram caption
            max_caption: Maximum characters for caption

        Returns:
            Dict with prepared data
        """
        try:
            # Instagram image requirements:
            # - Aspect ratios: 1:1 (square), 4:5 (portrait), 1.91:1 (landscape)
            # - Recommended: 1080x1080 for square
            # - Max 30 hashtags

            # Determine best aspect ratio
            width, height = image.size
            aspect = width / height

            if 0.9 <= aspect <= 1.1:
                # Square
                target_size = (1080, 1080)
            elif aspect < 0.9:
                # Portrait (4:5)
                target_size = (1080, 1350)
            else:
                # Landscape (1.91:1)
                target_size = (1080, 566)

            # Resize maintaining aspect ratio
            image.thumbnail(target_size, Image.Resampling.LANCZOS)

            # Create square canvas if needed for square post
            if target_size == (1080, 1080):
                canvas = Image.new("RGB", target_size, (255, 255, 255))
                paste_x = (1080 - image.width) // 2
                paste_y = (1080 - image.height) // 2
                canvas.paste(image, (paste_x, paste_y))
                image = canvas

            # Prepare caption with hashtags
            hashtags = [
                "#AIArt",
                "#GenerativeArt",
                "#DigitalArt",
                "#AIArtist",
                "#Lumira",
                "#MachineLearning",
                "#DeepLearning",
                "#ArtificialIntelligence",
                "#ContemporaryArt",
                "#ModernArt",
            ]

            caption_with_tags = f"{caption}\n\n{' '.join(hashtags)}"

            if len(caption_with_tags) > max_caption:
                caption_with_tags = caption

            return {
                "platform": "instagram",
                "image": image,
                "caption": caption_with_tags,
                "size": image.size,
                "format": "JPEG",
                "quality": 95,
            }

        except Exception as e:
            logger.error("instagram_prep_error", error=str(e))
            raise

    async def prepare_for_pinterest(
        self,
        image: Image.Image,
        title: str,
        description: str,
    ) -> dict[str, Any]:
        """Prepare image for Pinterest.

        Args:
            image: PIL Image to share
            title: Pin title
            description: Pin description

        Returns:
            Dict with prepared data
        """
        try:
            # Pinterest image requirements:
            # - Optimal aspect ratio: 2:3 (portrait)
            # - Recommended: 1000x1500
            # - Max file size: 32MB

            # Resize to Pinterest's optimal size
            target_size = (1000, 1500)
            image.thumbnail(target_size, Image.Resampling.LANCZOS)

            # Create canvas with optimal aspect ratio
            canvas = Image.new("RGB", target_size, (255, 255, 255))
            paste_x = (1000 - image.width) // 2
            paste_y = (1500 - image.height) // 2
            canvas.paste(image, (paste_x, paste_y))

            return {
                "platform": "pinterest",
                "image": canvas,
                "title": title[:100],  # Max 100 chars
                "description": description[:500],  # Max 500 chars
                "size": canvas.size,
                "format": "PNG",
            }

        except Exception as e:
            logger.error("pinterest_prep_error", error=str(e))
            raise

    async def generate_share_url(
        self,
        platform: str,
        image_url: str,
        text: str | None = None,
    ) -> str:
        """Generate sharing URL for platform.

        Args:
            platform: Social platform name
            image_url: URL of the image
            text: Optional text to share

        Returns:
            Sharing URL
        """
        try:
            if platform == "twitter":
                import urllib.parse

                params = {"url": image_url}
                if text:
                    params["text"] = text
                query = urllib.parse.urlencode(params)
                return f"https://twitter.com/intent/tweet?{query}"

            elif platform == "facebook":
                import urllib.parse

                query = urllib.parse.urlencode({"u": image_url})
                return f"https://www.facebook.com/sharer/sharer.php?{query}"

            elif platform == "pinterest":
                import urllib.parse

                params = {"url": image_url, "media": image_url}
                if text:
                    params["description"] = text
                query = urllib.parse.urlencode(params)
                return f"https://pinterest.com/pin/create/button/?{query}"

            else:
                raise ValueError(f"Unsupported platform: {platform}")

        except Exception as e:
            logger.error("share_url_error", platform=platform, error=str(e))
            raise

    async def generate_og_metadata(
        self,
        title: str,
        description: str,
        image_url: str,
        url: str,
    ) -> dict[str, str]:
        """Generate Open Graph metadata for social sharing.

        Args:
            title: Page title
            description: Page description
            image_url: Image URL
            url: Page URL

        Returns:
            Dict of OG meta tags
        """
        return {
            "og:title": title,
            "og:description": description,
            "og:image": image_url,
            "og:url": url,
            "og:type": "website",
            "twitter:card": "summary_large_image",
            "twitter:title": title,
            "twitter:description": description,
            "twitter:image": image_url,
        }


def get_social_sharing() -> SocialSharing:
    """Get social sharing instance.

    Returns:
        SocialSharing instance
    """
    return SocialSharing()
