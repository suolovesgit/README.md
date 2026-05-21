#!/usr/bin/env python3
"""
Render a source video as a terminal-style ASCII GIF for a GitHub README.

Requirements:
  - ffmpeg and ffprobe on PATH
  - Pillow: python -m pip install pillow
"""

from __future__ import annotations

import argparse
import math
import shutil
import subprocess
import tempfile
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


RAMP = " .'`^\",:;Il!i><~+_-?][}{1)(|\\/tfjrxnuvczXYUJCLQ0OZmwqpdbkhao*#MW&8%B@$"


def run(command: list[str]) -> None:
    subprocess.run(command, check=True)


def probe_size(video: Path) -> tuple[int, int]:
    output = subprocess.check_output(
        [
            "ffprobe",
            "-v",
            "error",
            "-select_streams",
            "v:0",
            "-show_entries",
            "stream=width,height",
            "-of",
            "csv=s=x:p=0",
            str(video),
        ],
        text=True,
    ).strip()
    width, height = output.split("x")
    return int(width), int(height)


def find_font() -> str | None:
    candidates = [
        Path("C:/Windows/Fonts/consola.ttf"),
        Path("C:/Windows/Fonts/cour.ttf"),
        Path("/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf"),
        Path("/Library/Fonts/Menlo.ttc"),
    ]
    for path in candidates:
        if path.exists():
            return str(path)
    return None


def brightness_to_char(value: int) -> str:
    index = round((value / 255) * (len(RAMP) - 1))
    return RAMP[index]


def render_frame(
    gray: bytes,
    cols: int,
    rows: int,
    frame_index: int,
    font: ImageFont.ImageFont,
    char_width: int,
    line_height: int,
    padding: int,
    bar_height: int,
    scale: int,
) -> Image.Image:
    body_width = cols * char_width
    body_height = rows * line_height
    width = (body_width + padding * 2) * scale
    height = (body_height + padding * 2 + bar_height) * scale
    image = Image.new("RGB", (width, height), "#120d1f")
    draw = ImageDraw.Draw(image)

    draw.rounded_rectangle([0, 0, width - 1, height - 1], radius=18 * scale, fill="#120d1f", outline="#2b183f", width=3 * scale)
    draw.rounded_rectangle([0, 0, width - 1, bar_height * scale], radius=18 * scale, fill="#8b4dff", outline="#2b183f", width=3 * scale)
    draw.rectangle([0, (bar_height - 8) * scale, width - 1, bar_height * scale], fill="#8b4dff")

    dot_y = 22 * scale
    for dot_index, color in enumerate(("#ffd76d", "#ff66c7", "#58c7ff")):
        dot_x = (22 + dot_index * 24) * scale
        draw.ellipse([dot_x - 7 * scale, dot_y - 7 * scale, dot_x + 7 * scale, dot_y + 7 * scale], fill=color, outline="#2b183f", width=2 * scale)

    header = f"bad-apple-ascii.exe  frame {frame_index:05d}"
    draw.text((92 * scale, 11 * scale), header, font=font, fill="#fff7fb")

    for row in range(rows):
        start = row * cols
        values = gray[start : start + cols]
        text = "".join(brightness_to_char(pixel) for pixel in values)
        draw.text((padding * scale, (bar_height + padding + row * line_height) * scale), text, font=font, fill="#fff7fb")

    return image


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("video", type=Path, help="Source video file. Use a file you have rights to use.")
    parser.add_argument("--out", type=Path, default=Path("assets/bad-apple-terminal.gif"))
    parser.add_argument("--fps", type=int, default=12)
    parser.add_argument("--cols", type=int, default=88)
    parser.add_argument("--max-frames", type=int, default=0, help="Optional test limit. 0 means render the full video.")
    parser.add_argument("--scale", type=int, default=2, help="Render scale for sharper text.")
    args = parser.parse_args()

    if not args.video.exists():
        raise SystemExit(f"Missing source video: {args.video}")
    if shutil.which("ffmpeg") is None or shutil.which("ffprobe") is None:
        raise SystemExit("ffmpeg and ffprobe must be available on PATH.")

    source_width, source_height = probe_size(args.video)
    rows = max(24, math.floor(args.cols * (source_height / source_width) * 0.48))
    font_path = find_font()
    font = ImageFont.truetype(font_path, 10 * args.scale) if font_path else ImageFont.load_default()
    sample_box = ImageDraw.Draw(Image.new("RGB", (1, 1))).textbbox((0, 0), "@", font=font)
    char_width = max(1, sample_box[2] - sample_box[0])
    line_height = max(1, sample_box[3] - sample_box[1] + 2 * args.scale)
    padding = 14
    bar_height = 44

    args.out.parent.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="bad-apple-ascii-") as temp_name:
        temp = Path(temp_name)
        raw_command = [
            "ffmpeg",
            "-v",
            "error",
            "-i",
            str(args.video),
            "-vf",
            f"fps={args.fps},scale={args.cols}:{rows}:flags=lanczos,format=gray",
            "-f",
            "rawvideo",
            "-pix_fmt",
            "gray",
            "-",
        ]
        process = subprocess.Popen(raw_command, stdout=subprocess.PIPE)
        assert process.stdout is not None

        frame_size = args.cols * rows
        frame_index = 0
        while True:
            chunk = process.stdout.read(frame_size)
            if len(chunk) < frame_size:
                break
            frame = render_frame(chunk, args.cols, rows, frame_index, font, char_width, line_height, padding, bar_height, args.scale)
            frame.save(temp / f"frame_{frame_index:06d}.png")
            frame_index += 1
            if args.max_frames and frame_index >= args.max_frames:
                process.kill()
                break

        if frame_index == 0:
            raise SystemExit("No frames were rendered.")

        palette = temp / "palette.png"
        run([
            "ffmpeg",
            "-v",
            "error",
            "-y",
            "-framerate",
            str(args.fps),
            "-i",
            str(temp / "frame_%06d.png"),
            "-vf",
            "palettegen",
            str(palette),
        ])
        run([
            "ffmpeg",
            "-v",
            "error",
            "-y",
            "-framerate",
            str(args.fps),
            "-i",
            str(temp / "frame_%06d.png"),
            "-i",
            str(palette),
            "-lavfi",
            "paletteuse=dither=bayer:bayer_scale=3",
            "-loop",
            "0",
            str(args.out),
        ])

    print(f"Rendered {frame_index} frames to {args.out}")


if __name__ == "__main__":
    main()
