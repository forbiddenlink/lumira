"""Best-effort content provenance metadata embedding.

Embeds C2PA-*shaped* provenance metadata in AI-generated images as a best-effort
transparency measure. This is NOT a full C2PA implementation: it writes an
unsigned manifest plus descriptive fields into PNG tEXt chunks / XMP, but does
NOT perform cryptographic C2PA signing (no signed C2PA claim, no tamper-evident
chain of custody). Treat it as informative metadata, not a verifiable
credential.

This may help toward transparency expectations such as the EU AI Act's
AI-generated-content disclosure, but on its own it does not establish
regulatory compliance, and the cryptographic signing that C2PA relies on for
tamper detection is not yet implemented.

Embedded metadata includes:
- AI generation disclosure (Lumira as the generating tool)
- Model information and parameters
- Creator attribution
- Timestamp
- An instance ID hash (identifier only, not a tamper-proof signature)

References:
- C2PA Specification: https://c2pa.org/specifications/
- EU AI Act Article 50: AI-generated content transparency requirements
"""

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

from PIL import Image
from PIL.PngImagePlugin import PngInfo

from ..utils.logging import get_logger

logger = get_logger(__name__)

# Check for c2pa library availability
try:
    import c2pa  # noqa: F401

    C2PA_AVAILABLE = True
except ImportError:
    C2PA_AVAILABLE = False
    logger.debug("c2pa library not installed, using fallback XMP metadata")


class ProvenanceMetadata:
    """C2PA-compatible provenance metadata for AI-generated images."""

    def __init__(
        self,
        generator_name: str = "Lumira",
        generator_version: str = "0.1.0",
        model_name: str | None = None,
        model_version: str | None = None,
    ):
        """Initialize provenance metadata generator.

        Args:
            generator_name: Name of the AI system
            generator_version: Version of the AI system
            model_name: Name of the AI model used
            model_version: Version of the AI model
        """
        self.generator_name = generator_name
        self.generator_version = generator_version
        self.model_name = model_name
        self.model_version = model_version

    def create_manifest(
        self,
        prompt: str,
        negative_prompt: str = "",
        seed: int | None = None,
        steps: int | None = None,
        guidance_scale: float | None = None,
        width: int | None = None,
        height: int | None = None,
        mood: str | None = None,
        style: str | None = None,
        additional_metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Create a C2PA-compatible manifest for an AI-generated image.

        Args:
            prompt: The text prompt used for generation
            negative_prompt: Negative prompt if used
            seed: Random seed for reproducibility
            steps: Number of inference steps
            guidance_scale: Classifier-free guidance scale
            width: Image width
            height: Image height
            mood: Lumira's mood during creation
            style: Artistic style applied
            additional_metadata: Any additional metadata to include

        Returns:
            C2PA-compatible manifest dictionary
        """
        timestamp = datetime.now(UTC).isoformat()

        manifest = {
            # C2PA required fields
            "claim_generator": f"{self.generator_name}/{self.generator_version}",
            "title": f"AI-Generated Artwork by {self.generator_name}",
            "format": "image/png",
            "instance_id": self._generate_instance_id(prompt, timestamp),
            # AI generation disclosure (EU AI Act requirement)
            "assertions": [
                {
                    "label": "c2pa.ai_disclosure",
                    "data": {
                        "ai_generated": True,
                        "ai_tool": self.generator_name,
                        "ai_tool_version": self.generator_version,
                        "disclosure_type": "fully_ai_generated",
                    },
                },
                {
                    "label": "c2pa.actions",
                    "data": {
                        "actions": [
                            {
                                "action": "c2pa.created",
                                "when": timestamp,
                                "softwareAgent": f"{self.generator_name} {self.generator_version}",
                                "parameters": {
                                    "model": self.model_name or "unknown",
                                    "model_version": self.model_version or "unknown",
                                },
                            }
                        ]
                    },
                },
            ],
            # Lumira-specific metadata
            "lumira": {
                "prompt": prompt,
                "negative_prompt": negative_prompt,
                "seed": seed,
                "steps": steps,
                "guidance_scale": guidance_scale,
                "width": width,
                "height": height,
                "mood": mood,
                "style": style,
                "created_at": timestamp,
            },
        }

        # Add any additional metadata
        if additional_metadata:
            lumira_data = manifest["lumira"]
            if isinstance(lumira_data, dict):
                lumira_data.update(additional_metadata)

        return manifest

    def _generate_instance_id(self, prompt: str, timestamp: str) -> str:
        """Generate a unique instance ID for the image.

        Args:
            prompt: The generation prompt
            timestamp: Creation timestamp

        Returns:
            Unique instance ID (URN format)
        """
        content = f"{prompt}{timestamp}{self.generator_name}"
        hash_value = hashlib.sha256(content.encode()).hexdigest()[:16]
        return f"urn:uuid:lumira-{hash_value}"

    def embed_in_png(
        self,
        image: Image.Image,
        manifest: dict[str, Any],
        output_path: Path | None = None,
    ) -> Image.Image:
        """Embed C2PA-compatible metadata in a PNG image.

        Uses PNG tEXt/iTXt chunks to store metadata. For full C2PA compliance,
        use the c2pa library when available.

        Args:
            image: PIL Image to embed metadata in
            manifest: C2PA manifest dictionary
            output_path: Optional path to save the image

        Returns:
            PIL Image with embedded metadata
        """
        # Create PNG metadata
        pnginfo = PngInfo()

        # Add C2PA-compatible metadata as JSON
        manifest_json = json.dumps(manifest, indent=2, default=str)
        pnginfo.add_text("c2pa:manifest", manifest_json)

        # Add individual fields for compatibility with various tools
        pnginfo.add_text("Software", f"{self.generator_name} {self.generator_version}")
        pnginfo.add_text("Comment", "AI-generated image")
        pnginfo.add_text("Author", self.generator_name)

        # Add Lumira-specific fields
        lumira_data = manifest.get("lumira", {})
        if lumira_data.get("prompt"):
            pnginfo.add_text("Description", lumira_data["prompt"][:500])
        if lumira_data.get("mood"):
            pnginfo.add_text("lumira:mood", lumira_data["mood"])
        if lumira_data.get("style"):
            pnginfo.add_text("lumira:style", lumira_data["style"])

        # Add generation parameters (compatible with Automatic1111 format)
        params = []
        if lumira_data.get("prompt"):
            params.append(lumira_data["prompt"])
        if lumira_data.get("negative_prompt"):
            params.append(f"Negative prompt: {lumira_data['negative_prompt']}")

        gen_params = []
        if lumira_data.get("steps"):
            gen_params.append(f"Steps: {lumira_data['steps']}")
        if lumira_data.get("guidance_scale"):
            gen_params.append(f"CFG scale: {lumira_data['guidance_scale']}")
        if lumira_data.get("seed"):
            gen_params.append(f"Seed: {lumira_data['seed']}")
        if lumira_data.get("width") and lumira_data.get("height"):
            gen_params.append(f"Size: {lumira_data['width']}x{lumira_data['height']}")
        if self.model_name:
            gen_params.append(f"Model: {self.model_name}")

        if gen_params:
            params.append(", ".join(gen_params))

        if params:
            pnginfo.add_text("parameters", "\n".join(params))

        # Save with metadata if output path provided
        if output_path:
            image.save(output_path, "PNG", pnginfo=pnginfo)
            logger.info(
                "provenance_metadata_embedded",
                path=str(output_path),
                instance_id=manifest.get("instance_id"),
            )
            return Image.open(output_path)

        # Return image with metadata attached for later saving
        image.info["pnginfo"] = pnginfo
        return image

    def embed_xmp_metadata(
        self,
        image: Image.Image,
        manifest: dict[str, Any],
    ) -> bytes:
        """Generate XMP metadata for embedding in various image formats.

        XMP (Extensible Metadata Platform) is widely supported across image formats
        and provides a fallback when full C2PA is not available.

        Args:
            image: PIL Image
            manifest: C2PA manifest dictionary

        Returns:
            XMP metadata as bytes
        """
        lumira_data = manifest.get("lumira", {})
        timestamp = lumira_data.get("created_at", datetime.now(UTC).isoformat())

        xmp = f"""<?xpacket begin="" id="W5M0MpCehiHzreSzNTczkc9d"?>
<x:xmpmeta xmlns:x="adobe:ns:meta/">
  <rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#">
    <rdf:Description rdf:about=""
        xmlns:dc="http://purl.org/dc/elements/1.1/"
        xmlns:xmp="http://ns.adobe.com/xap/1.0/"
        xmlns:xmpRights="http://ns.adobe.com/xap/1.0/rights/"
        xmlns:Iptc4xmpExt="http://iptc.org/std/Iptc4xmpExt/2008-02-29/"
        xmlns:lumira="http://lumira.art/ns/1.0/">

      <dc:creator>
        <rdf:Seq>
          <rdf:li>{self.generator_name}</rdf:li>
        </rdf:Seq>
      </dc:creator>
      <dc:description>
        <rdf:Alt>
          <rdf:li xml:lang="x-default">{lumira_data.get("prompt", "AI-generated artwork")[:500]}</rdf:li>
        </rdf:Alt>
      </dc:description>

      <xmp:CreatorTool>{self.generator_name} {self.generator_version}</xmp:CreatorTool>
      <xmp:CreateDate>{timestamp}</xmp:CreateDate>

      <Iptc4xmpExt:DigitalSourceType>http://cv.iptc.org/newscodes/digitalsourcetype/trainedAlgorithmicMedia</Iptc4xmpExt:DigitalSourceType>

      <lumira:aiGenerated>true</lumira:aiGenerated>
      <lumira:model>{self.model_name or "unknown"}</lumira:model>
      <lumira:mood>{lumira_data.get("mood", "")}</lumira:mood>
      <lumira:style>{lumira_data.get("style", "")}</lumira:style>
      <lumira:seed>{lumira_data.get("seed", "")}</lumira:seed>

    </rdf:Description>
  </rdf:RDF>
</x:xmpmeta>
<?xpacket end="w"?>"""

        return xmp.encode("utf-8")


class ProvenanceManager:
    """High-level manager for AI content provenance."""

    def __init__(
        self, generator_name: str = "Lumira", generator_version: str = "0.1.0"
    ):
        """Initialize provenance manager.

        Args:
            generator_name: Name of the AI system
            generator_version: Version of the AI system
        """
        self.metadata = ProvenanceMetadata(generator_name, generator_version)
        self.c2pa_available = C2PA_AVAILABLE

    def set_model(self, model_name: str, model_version: str | None = None) -> None:
        """Set the AI model information.

        Args:
            model_name: Name of the AI model
            model_version: Version of the AI model
        """
        self.metadata.model_name = model_name
        self.metadata.model_version = model_version

    def embed_provenance(
        self,
        image: Image.Image,
        output_path: Path,
        prompt: str,
        negative_prompt: str = "",
        seed: int | None = None,
        steps: int | None = None,
        guidance_scale: float | None = None,
        mood: str | None = None,
        style: str | None = None,
        **kwargs: Any,
    ) -> Path:
        """Embed full provenance metadata in an image.

        Args:
            image: PIL Image to embed metadata in
            output_path: Path to save the image with metadata
            prompt: Generation prompt
            negative_prompt: Negative prompt
            seed: Random seed
            steps: Inference steps
            guidance_scale: CFG scale
            mood: Lumira's mood
            style: Artistic style
            **kwargs: Additional metadata

        Returns:
            Path to the saved image with provenance metadata
        """
        # Create manifest
        manifest = self.metadata.create_manifest(
            prompt=prompt,
            negative_prompt=negative_prompt,
            seed=seed,
            steps=steps,
            guidance_scale=guidance_scale,
            width=image.width,
            height=image.height,
            mood=mood,
            style=style,
            additional_metadata=kwargs if kwargs else None,
        )

        # Embed using best available method. NOTE: cryptographic C2PA signing is
        # not yet implemented, so both branches currently write unsigned PNG
        # metadata (see _embed_c2pa).
        if self.c2pa_available:
            return self._embed_c2pa(image, manifest, output_path)
        else:
            # Fallback to PNG metadata embedding
            self.metadata.embed_in_png(image, manifest, output_path)
            return output_path

    def _embed_c2pa(
        self,
        image: Image.Image,
        manifest: dict[str, Any],
        output_path: Path,
    ) -> Path:
        """Embed provenance metadata (unsigned).

        Placeholder for full C2PA cryptographic signing via the c2pa-python
        library. That signing is NOT yet implemented, so this currently writes
        the same unsigned PNG metadata as the fallback path.

        Args:
            image: PIL Image
            manifest: C2PA manifest
            output_path: Output path

        Returns:
            Path to saved image
        """
        # Cryptographic C2PA signing (c2pa-python) is not yet implemented; write
        # unsigned PNG metadata instead. Do NOT present this as a signed claim.
        logger.warning(
            "c2pa_full_not_implemented",
            message="Full C2PA with signatures not yet implemented, using PNG metadata",
        )
        self.metadata.embed_in_png(image, manifest, output_path)
        return output_path

    def verify_provenance(self, image_path: Path) -> dict[str, Any] | None:
        """Verify and extract provenance metadata from an image.

        Args:
            image_path: Path to the image

        Returns:
            Provenance metadata if found, None otherwise
        """
        try:
            image = Image.open(image_path)

            # Check for C2PA manifest in PNG metadata
            if "c2pa:manifest" in image.info:
                manifest_json = image.info["c2pa:manifest"]
                if isinstance(manifest_json, str):
                    return cast(dict[str, Any], json.loads(manifest_json))

            # Check for standard metadata fields
            metadata = {}
            for key in ["parameters", "Description", "Software", "Comment"]:
                if key in image.info:
                    metadata[key] = image.info[key]

            return metadata if metadata else None

        except Exception as e:
            logger.error(
                "provenance_verification_failed", path=str(image_path), error=str(e)
            )
            return None


def get_provenance_manager() -> ProvenanceManager:
    """Get provenance manager instance.

    Returns:
        ProvenanceManager instance
    """
    return ProvenanceManager()
