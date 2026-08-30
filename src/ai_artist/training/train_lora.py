"""LoRA training script for Stable Diffusion fine-tuning."""

import argparse
import math
from pathlib import Path
from typing import Any

import torch
from accelerate import Accelerator
from diffusers import AutoencoderKL, DDPMScheduler, UNet2DConditionModel
from diffusers.optimization import get_scheduler
from peft import LoraConfig, get_peft_model
from PIL import Image
from torch.utils.data import Dataset
from torchvision import transforms
from tqdm.auto import tqdm
from transformers import CLIPTextModel, CLIPTokenizer

from ai_artist.utils.logging import get_logger

logger = get_logger(__name__)


class DreamBoothDataset(Dataset):
    """Dataset for DreamBooth-style training."""

    def __init__(
        self,
        instance_data_root: Path,
        tokenizer: Any,
        size: int = 512,
        center_crop: bool = True,
    ) -> None:
        self.size = size
        self.center_crop = center_crop
        self.tokenizer = tokenizer

        # Filter for image files only
        valid_extensions = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}
        self.instance_images_path = [
            p
            for p in Path(instance_data_root).iterdir()
            if p.suffix.lower() in valid_extensions
        ]
        self.num_instance_images = len(self.instance_images_path)

        self._length = self.num_instance_images

        self.image_transforms = transforms.Compose(
            [
                transforms.Resize(
                    size, interpolation=transforms.InterpolationMode.BILINEAR
                ),
                (
                    transforms.CenterCrop(size)
                    if center_crop
                    else transforms.RandomCrop(size)
                ),
                transforms.ToTensor(),
                transforms.Normalize([0.5], [0.5]),
            ]
        )

    def __len__(self) -> int:
        return self._length

    def __getitem__(self, index: int) -> dict[str, Any]:
        example = {}
        instance_image = Image.open(
            self.instance_images_path[index % self.num_instance_images]
        )
        rgb_image: Image.Image = instance_image
        if rgb_image.mode != "RGB":
            rgb_image = rgb_image.convert("RGB")
        example["instance_images"] = self.image_transforms(rgb_image)

        # Simple prompt for style training
        example["instance_prompt_ids"] = self.tokenizer(
            "a photo",
            truncation=True,
            padding="max_length",
            max_length=self.tokenizer.model_max_length,
            return_tensors="pt",
        ).input_ids

        return example


def train_lora(
    pretrained_model_name: str,
    instance_data_dir: Path,
    output_dir: Path,
    rank: int = 4,
    learning_rate: float = 1e-4,
    max_train_steps: int = 2000,
    train_batch_size: int = 1,
    gradient_accumulation_steps: int = 4,
    lr_scheduler: str = "constant",
    lr_warmup_steps: int = 0,
    resolution: int = 512,
    mixed_precision: str = "no",
) -> None:
    """Train a LoRA adapter for Stable Diffusion."""

    # Initialize accelerator
    accelerator = Accelerator(
        gradient_accumulation_steps=gradient_accumulation_steps,
        mixed_precision=mixed_precision,
    )

    logger.info(
        "training_started",
        model=pretrained_model_name,
        rank=rank,
        steps=max_train_steps,
    )

    # Load models
    tokenizer = CLIPTokenizer.from_pretrained(
        pretrained_model_name,
        subfolder="tokenizer",
    )

    text_encoder = CLIPTextModel.from_pretrained(
        pretrained_model_name,
        subfolder="text_encoder",
    )

    vae = AutoencoderKL.from_pretrained(
        pretrained_model_name,
        subfolder="vae",
    )

    unet = UNet2DConditionModel.from_pretrained(
        pretrained_model_name,
        subfolder="unet",
    )

    # Freeze vae and text_encoder
    vae.requires_grad_(False)
    text_encoder.requires_grad_(False)

    # Add LoRA layers
    lora_config = LoraConfig(
        r=rank,
        lora_alpha=rank,
        init_lora_weights="gaussian",
        target_modules=["to_k", "to_q", "to_v", "to_out.0"],
    )

    unet = get_peft_model(unet, lora_config)
    unet.print_trainable_parameters()

    # Optimizer
    optimizer = torch.optim.AdamW(
        unet.parameters(),
        lr=learning_rate,
    )

    # Noise scheduler
    noise_scheduler = DDPMScheduler.from_pretrained(
        pretrained_model_name,
        subfolder="scheduler",
    )

    # Dataset and dataloader
    train_dataset = DreamBoothDataset(
        instance_data_root=instance_data_dir,
        tokenizer=tokenizer,
        size=resolution,
    )

    train_dataloader = torch.utils.data.DataLoader(
        train_dataset,
        batch_size=train_batch_size,
        shuffle=True,
        num_workers=0,
    )

    # LR scheduler
    lr_scheduler_obj = get_scheduler(
        lr_scheduler,
        optimizer=optimizer,
        num_warmup_steps=lr_warmup_steps * gradient_accumulation_steps,
        num_training_steps=max_train_steps * gradient_accumulation_steps,
    )

    # Prepare with accelerator
    unet, optimizer, train_dataloader, lr_scheduler_obj = accelerator.prepare(
        unet, optimizer, train_dataloader, lr_scheduler_obj
    )

    # Move vae and text_encoder to device
    vae.to(accelerator.device)
    text_encoder.to(accelerator.device)

    # Training loop
    global_step = 0
    progress_bar = tqdm(
        range(max_train_steps),
        disable=not accelerator.is_local_main_process,
    )
    progress_bar.set_description("Steps")

    num_epochs = math.ceil(max_train_steps / len(train_dataloader))
    for _epoch in range(num_epochs):
        unet.train()

        for _step, batch in enumerate(train_dataloader):
            with accelerator.accumulate(unet):
                # Convert images to latent space
                latents = vae.encode(batch["instance_images"]).latent_dist.sample()
                latents = latents * vae.config.scaling_factor

                # Sample noise
                noise = torch.randn_like(latents)
                bsz = latents.shape[0]

                # Sample timesteps
                timesteps = torch.randint(
                    0,
                    noise_scheduler.config.num_train_timesteps,
                    (bsz,),
                    device=latents.device,
                )
                timesteps = timesteps.long()

                # Add noise to latents
                noisy_latents = noise_scheduler.add_noise(latents, noise, timesteps)

                # Get text embeddings
                encoder_hidden_states = text_encoder(batch["instance_prompt_ids"])[0]

                # Predict noise
                model_pred = unet(
                    noisy_latents, timesteps, encoder_hidden_states
                ).sample

                # Get target
                target = noise

                # Calculate loss
                loss = torch.nn.functional.mse_loss(
                    model_pred.float(), target.float(), reduction="mean"
                )

                # Backprop
                accelerator.backward(loss)

                if accelerator.sync_gradients:
                    accelerator.clip_grad_norm_(unet.parameters(), 1.0)

                optimizer.step()
                lr_scheduler_obj.step()
                optimizer.zero_grad()

            # Update progress
            if accelerator.sync_gradients:
                progress_bar.update(1)
                global_step += 1

                if global_step % 100 == 0:
                    logger.info(
                        "training_progress",
                        step=global_step,
                        loss=float(loss.detach().item()),
                    )

            logs = {
                "loss": loss.detach().item(),
                "lr": lr_scheduler_obj.get_last_lr()[0],
            }
            progress_bar.set_postfix(**logs)

            if global_step >= max_train_steps:
                break

    # Save LoRA weights
    accelerator.wait_for_everyone()
    if accelerator.is_main_process:
        unet = accelerator.unwrap_model(unet)
        unet.save_pretrained(output_dir)
        logger.info("training_complete", output_dir=str(output_dir))

    accelerator.end_training()


def main() -> None:
    """CLI entry point."""
    parser = argparse.ArgumentParser(description="Train LoRA for Stable Diffusion")
    parser.add_argument(
        "--pretrained_model",
        type=str,
        default="runwayml/stable-diffusion-v1-5",
        help="Pretrained model name or path",
    )
    parser.add_argument(
        "--instance_data_dir",
        type=Path,
        required=True,
        help="Directory containing training images",
    )
    parser.add_argument(
        "--output_dir",
        type=Path,
        default=Path("models/lora"),
        help="Output directory for LoRA weights",
    )
    parser.add_argument(
        "--rank",
        type=int,
        default=4,
        help="LoRA rank (4-128, lower is faster)",
    )
    parser.add_argument(
        "--learning_rate",
        type=float,
        default=1e-4,
        help="Learning rate",
    )
    parser.add_argument(
        "--max_train_steps",
        type=int,
        default=2000,
        help="Maximum training steps",
    )
    parser.add_argument(
        "--train_batch_size",
        type=int,
        default=1,
        help="Training batch size",
    )
    parser.add_argument(
        "--gradient_accumulation_steps",
        type=int,
        default=4,
        help="Gradient accumulation steps",
    )
    parser.add_argument(
        "--resolution",
        type=int,
        default=512,
        help="Image resolution",
    )
    parser.add_argument(
        "--mixed_precision",
        type=str,
        default="no",
        choices=["no", "fp16", "bf16"],
        help="Mixed precision training",
    )

    args = parser.parse_args()

    # Create output directory
    args.output_dir.mkdir(parents=True, exist_ok=True)

    train_lora(
        pretrained_model_name=args.pretrained_model,
        instance_data_dir=args.instance_data_dir,
        output_dir=args.output_dir,
        rank=args.rank,
        learning_rate=args.learning_rate,
        max_train_steps=args.max_train_steps,
        train_batch_size=args.train_batch_size,
        gradient_accumulation_steps=args.gradient_accumulation_steps,
        resolution=args.resolution,
        mixed_precision=args.mixed_precision,
    )


if __name__ == "__main__":
    main()
