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

## Requirements

- Python 3.8+

## Installation

```bash
git clone https://github.com/jordan-gleeson/world-anvil-to-pdf.git
cd world-anvil-to-pdf
pip install -r requirements.txt
```

## Usage

1. Export your world from World Anvil (Settings > Export)
2. Place the export ZIP file in the `input/` folder
3. Run the script:

```bash
python wa_combiner.py
```

The script will automatically find the export ZIP with the most recent date in its filename, extract it, and generate a PDF in the `output/` folder.

You can also place an already-extracted export folder in `input/` instead of a ZIP.

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

## License

This project is licensed under the MIT License. See [LICENSE](LICENSE) for details.

The included `DejaVuSans.ttf` font is licensed under the [DejaVu Fonts License](https://dejavu-fonts.github.io/License.html).
