# World Anvil to PDF

Convert [World Anvil](https://www.worldanvil.com/) exports into a readable PDF document.

This tool takes a World Anvil JSON export folder and combines all articles (and secrets) into a single PDF, preserving titles, headings, tables, and images.

## Features

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
git clone https://github.com/YOUR_USERNAME/world-anvil-to-pdf.git
cd world-anvil-to-pdf
pip install -r requirements.txt
```

## Usage

1. Export your world from World Anvil (Settings > Export)
2. Extract the export ZIP into a folder
3. Run the script from the directory containing your export folder:

```bash
python wa_combiner.py
```

The script will automatically find the latest export directory (by date), combine all article and secret JSON files, and generate a PDF.

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

The script reads the JSON files from `articles/` and `secrets/`, downloads any referenced images, and produces a combined PDF.

## License

This project is licensed under the MIT License. See [LICENSE](LICENSE) for details.

The included `DejaVuSans.ttf` font is licensed under the [DejaVu Fonts License](https://dejavu-fonts.github.io/License.html).
