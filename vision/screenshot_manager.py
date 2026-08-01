from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import logging
from pathlib import Path
from typing import TypeAlias

import pyautogui
from PIL import Image


LOGGER = logging.getLogger(__name__)

Region: TypeAlias = tuple[int, int, int, int]


@dataclass(frozen=True)
class ScreenshotResult:
    path: Path
    width: int
    height: int
    created_at: datetime
    region: Region | None = None


class ScreenshotManager:
    def __init__(
        self,
        output_dir: str | Path = "screenshots/vision",
        image_format: str = "png",
    ) -> None:
        self.output_dir = Path(output_dir)
        self.image_format = image_format.lower().lstrip(".")

    def capture(
        self,
        region: Region | None = None,
        filename: str | None = None,
        max_size: tuple[int, int] | None = None,
    ) -> ScreenshotResult:
        self.output_dir.mkdir(parents=True, exist_ok=True)
        created_at = datetime.now()
        image = pyautogui.screenshot(region=region)

        if max_size:
            image = self.resize_image(image, max_size)

        path = self.output_dir / (filename or self._default_filename(created_at))
        image.save(path)

        LOGGER.info("Screenshot saved: %s", path)
        return ScreenshotResult(
            path=path.resolve(),
            width=image.width,
            height=image.height,
            created_at=created_at,
            region=region,
        )

    def crop_existing(
        self,
        image_path: str | Path,
        region: Region,
        output_filename: str | None = None,
    ) -> ScreenshotResult:
        source = Path(image_path)
        if not source.is_file():
            raise FileNotFoundError(f"Screenshot not found: {source}")

        left, top, width, height = region
        with Image.open(source) as image:
            cropped = image.crop((left, top, left + width, top + height))
            created_at = datetime.now()
            self.output_dir.mkdir(parents=True, exist_ok=True)
            target = self.output_dir / (output_filename or self._default_filename(created_at, suffix="crop"))
            cropped.save(target)

        LOGGER.info("Cropped screenshot saved: %s", target)
        return ScreenshotResult(
            path=target.resolve(),
            width=cropped.width,
            height=cropped.height,
            created_at=created_at,
            region=region,
        )

    def resize_existing(
        self,
        image_path: str | Path,
        max_size: tuple[int, int],
        output_filename: str | None = None,
    ) -> ScreenshotResult:
        source = Path(image_path)
        if not source.is_file():
            raise FileNotFoundError(f"Screenshot not found: {source}")

        with Image.open(source) as image:
            resized = self.resize_image(image, max_size)
            created_at = datetime.now()
            self.output_dir.mkdir(parents=True, exist_ok=True)
            target = self.output_dir / (output_filename or self._default_filename(created_at, suffix="resize"))
            resized.save(target)

        LOGGER.info("Resized screenshot saved: %s", target)
        return ScreenshotResult(
            path=target.resolve(),
            width=resized.width,
            height=resized.height,
            created_at=created_at,
        )

    def resize_image(self, image: Image.Image, max_size: tuple[int, int]) -> Image.Image:
        resized = image.copy()
        resized.thumbnail(max_size, Image.Resampling.LANCZOS)
        return resized

    def _default_filename(self, created_at: datetime, suffix: str | None = None) -> str:
        stamp = created_at.strftime("%Y%m%d-%H%M%S-%f")
        name = f"screenshot_{stamp}"
        if suffix:
            name += f"_{suffix}"
        return f"{name}.{self.image_format}"
