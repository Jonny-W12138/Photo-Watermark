# Photo Watermark (EXIF Date)

A simple Python CLI that reads each image's EXIF capture time (YYYY-MM-DD) and places it as a text watermark onto the image. Results are saved into a subdirectory named `<source_dir>_watermark` under the source directory.

## Install

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Usage

Process a single file's directory (i.e., all images in that file's directory):
```bash
python watermark.py /path/to/image.jpg
```

Process a directory directly:
```bash
python watermark.py /path/to/images_dir
```

Options:
```bash
--font-size INT        Font size (default: 36)
--color COLOR          Text color hex or name, supports alpha. e.g. #FFFFFFCC
--position POS         One of: top-left, top-center, top-right,
                       center-left, center, center-right,
                       bottom-left, bottom-center, bottom-right
--margin INT           Margin in pixels from edges (default: 24)
--font PATH            Path to a .ttf/.otf font. If omitted, auto-detect
```

Examples:
```bash
python watermark.py ./photos --font-size 48 --color "#FFCC00CC" --position bottom-right
python watermark.py ./photos/IMG_0001.JPG --position top-left --font /Library/Fonts/Arial.ttf
```

Notes:
- Only images with EXIF date will be watermarked; others are skipped.
- Supported formats: JPG/JPEG, PNG, WEBP, TIFF, BMP.
- Output file names are suffixed with `_watermark` before the extension.
```
IMG_0001.JPG -> IMG_0001_watermark.JPG
```