# World Anvil to PDF

Convert [World Anvil](https://www.worldanvil.com/) exports into a readable PDF document.

This tool takes a World Anvil JSON export and combines all articles (and secrets) into a single PDF, preserving titles, headings, tables, and images.

## Features

- Automatically extracts World Anvil export ZIP files
- Selects the most recent export by date if multiple are present
- Parses World Anvil BBCode formatting (headings, tables, bold, etc.)
- Downloads and embeds article images (portraits, covers, inline images)
- Converts WebP images to PNG automatically
- Handles secrets with a `(SECRET)` label
- Extracts additional article sections (demographics, history, geography, etc.)
- Cleans up World Anvil-specific tags, UUIDs, and cross-references

## Standalone Executable (no Python required)

Download the latest `wa_combiner.exe` from the [Releases](https://github.com/jordan-gleeson/world-anvil-to-pdf/releases) page. Place it in a folder, create an `input/` subfolder, drop your World Anvil export ZIP inside, and double-click the exe (or run it from a terminal).

## Requirements (Python)

- Python 3.8+

## Installation

```bash
git clone https://github.com/jordan-gleeson/world-anvil-to-pdf.git
cd world-anvil-to-pdf
pip install -r requirements.txt
```

## Usage

1. Export your world from World Anvil (https://www.worldanvil.com/learn/world/export)
2. Place the export ZIP file in the `input/` folder
3. Run the script:

```bash
python wa_combiner.py
```

The script will automatically find the export ZIP with the most recent date in its filename, extract it, and generate a PDF in the `output/` folder.

You can also place an already-extracted export folder in `input/` instead of a ZIP.

### Options

```bash
python wa_combiner.py --help
```

| Flag | Description | Default |
|------|-------------|---------|
| `-i`, `--input` | Input directory containing export ZIPs or folders | `input/` folder |
| `-o`, `--output` | Output directory for generated PDF | `output/` folder |
| `-c`, `--cache` | Cache directory for downloaded images | `cache/` folder |
| `-f`, `--font` | Path to a `.ttf` font file | `DejaVuSans.ttf` |
| `--no-secrets` | Exclude secret articles from the PDF | Include secrets |

### Examples

```bash
# Use custom input and output directories
python wa_combiner.py --input ./my_exports --output ./pdfs

# Use a different font
python wa_combiner.py --font /path/to/MyFont.ttf

# Exclude secrets from the PDF
python wa_combiner.py --no-secrets
```

## Folder Structure

```
world-anvil-to-pdf/
  wa_combiner.py
  DejaVuSans.ttf
  requirements.txt
  input/              <-- place your export ZIP here
  output/             <-- generated PDF appears here
  cache/              <-- downloaded images cached per world
```

## How World Anvil Exports Work

A World Anvil export is a ZIP containing a folder structure like:

```
World-YourWorld-YYYY-MM-DD/
  World-YourWorld-xxx/
    articles/
      article-name-abc123.json
      ...
    secrets/
      secret-name-def456.json
      ...
    images/
      image-name-789.json
      ...
```

The script locates the `articles/` and `secrets/` directories within the export, downloads any referenced images, and produces a combined PDF.

## Troubleshooting

- **"No World Anvil export ZIPs or folders found"** — Place the export ZIP in the `input/` folder, or use `--input` to point to a different directory.
- **"Font file not found"** — Ensure `DejaVuSans.ttf` is in the same directory as the script, or use `--font` to provide a path to any `.ttf` font file.
- **"No JSON files found"** — The export may be empty or have an unexpected structure. Check that the ZIP contains `articles/` with `.json` files inside.
- **Images not appearing** — Images are downloaded from World Anvil's servers. Check your internet connection and that the export contains an `images/` directory.

## Building the Executable

To build the standalone `.exe` yourself:

```bash
pip install pyinstaller
pyinstaller wa_combiner.spec
```

The executable will be created at `dist/wa_combiner.exe` with the font bundled inside.

## Running Tests

```bash
pip install pytest
pytest test_wa_combiner.py -v
```

## License

This project is licensed under the MIT License. See [LICENSE](LICENSE) for details.

The included `DejaVuSans.ttf` font is licensed under the [DejaVu Fonts License](https://dejavu-fonts.github.io/License.html).
