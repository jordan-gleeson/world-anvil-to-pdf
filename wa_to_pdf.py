from __future__ import annotations

import argparse
import atexit
import json
import os
import sys
import zipfile
from fpdf import FPDF
from html import unescape
import re
import requests
from PIL import Image

def parse_wa_table(table_text):
    """
    Parse World Anvil BBCode [table]...[/table] into a list of rows, each a list of cells.
    Returns (rows, is_header_row_present)
    """
    # Remove [table] and [/table]
    table_body = re.sub(r'^\[table\]|\[/table\]$', '', table_text.strip(), flags=re.IGNORECASE)
    # Split into rows
    row_texts = re.findall(r'\[tr\](.*?)\[/tr\]', table_body, flags=re.DOTALL|re.IGNORECASE)
    rows = []
    is_header = False
    for row in row_texts:
        # Find header cells
        headers = re.findall(r'\[th\](.*?)\[/th\]', row, flags=re.IGNORECASE)
        if headers:
            rows.append([h.strip() for h in headers])
            is_header = True
            continue
        # Find normal cells
        cells = re.findall(r'\[td\](.*?)\[/td\]', row, flags=re.IGNORECASE)
        rows.append([c.strip() for c in cells])
    return rows, is_header

def get_lines(pdf, width, text):
    """
    Split text into lines that fit within width using pdf.get_string_width.
    """
    lines = []
    # Handle explicit newlines
    paragraphs = text.split('\n')
    for paragraph in paragraphs:
        if not paragraph:
            lines.append('')
            continue
        words = paragraph.split(' ')
        current_line = []
        current_width = 0
        for word in words:
            # Add space width if not first word
            w_width = pdf.get_string_width(word)
            space_width = pdf.get_string_width(' ')
            
            if not current_line:
                if w_width > width:
                    # Word is too long, just add it (or split it, but simple is better)
                    lines.append(word)
                    current_width = 0
                else:
                    current_line.append(word)
                    current_width = w_width
            else:
                if current_width + space_width + w_width <= width:
                    current_line.append(word)
                    current_width += space_width + w_width
                else:
                    lines.append(' '.join(current_line))
                    current_line = [word]
                    current_width = w_width
        if current_line:
            lines.append(' '.join(current_line))
    return lines

def render_table(pdf, rows, is_header):
    """
    Render a table in the PDF using FPDF, given rows and header flag.
    """
    if not rows:
        return
    col_count = max(len(r) for r in rows)
    page_width = pdf.w - pdf.l_margin - getattr(pdf, 'r_margin', pdf.l_margin)
    col_width = page_width / col_count if col_count else page_width
    th_style = {'fill': True, 'text_color': (255,255,255), 'bg_color': (60,60,60)}
    normal_style = {'fill': False, 'text_color': (0,0,0), 'bg_color': (255,255,255)}


    for i, row in enumerate(rows):
        # Prepare cell styles
        if is_header and i == 0:
            pdf.set_fill_color(*th_style['bg_color'])
            pdf.set_text_color(*th_style['text_color'])
            pdf.set_font('DejaVu', '', 10)
        else:
            pdf.set_fill_color(*normal_style['bg_color'])
            pdf.set_text_color(*normal_style['text_color'])
            pdf.set_font('DejaVu', '', 10)

        # Calculate the height needed for each cell in this row
        cell_heights = []
        for cell in row:
            cell = clean_world_anvil_text(cell)
            lines = get_lines(pdf, col_width, cell)
            cell_heights.append(6 * len(lines) if lines else 6)
        max_height = max(cell_heights) if cell_heights else 6

        x_start = pdf.get_x()
        y_start = pdf.get_y()

        # Draw each cell in the row
        for j, cell in enumerate(row):
            x = x_start + j * col_width
            y = y_start
            pdf.set_xy(x, y)
            # Draw background fill
            if (is_header and i == 0):
                pdf.set_fill_color(*th_style['bg_color'])
            else:
                pdf.set_fill_color(*normal_style['bg_color'])
            pdf.rect(x, y, col_width, max_height, style='F')
            # Draw border
            pdf.rect(x, y, col_width, max_height)
            # Print text (centered vertically and horizontally)
            # Calculate vertical offset for centering
            text_height = cell_heights[j]
            y_text = y + (max_height - text_height) / 2 if max_height > text_height else y
            pdf.set_xy(x, y_text)
            pdf.multi_cell(col_width, 6, cell, border=0, align='L')

        # Move to the next line (max row height)
        pdf.set_xy(x_start, y_start + max_height)

    # Reset text color
    pdf.set_text_color(0,0,0)
    pdf.set_font('DejaVu', '', 10)

def find_non_content_images(data):
    """Recursively finds all image URLs and IDs in the JSON data, skipping the 'content' field."""
    images = []
    if isinstance(data, dict):
        for key, value in data.items():
            if key == 'content':
                continue  # Skip the main content field

            # Check for portrait-style image objects with a URL
            if key == 'portrait' and isinstance(value, dict) and 'url' in value:
                images.append({'url': value['url']})
            # Check for cover-style image objects, ignoring default covers
            elif key == 'cover' and isinstance(value, dict) and 'url' in value and 'Default Cover' not in value.get('title', ''):
                images.append({'url': value['url']})
            # Recurse into other dictionaries or lists
            elif isinstance(value, (dict, list)):
                images.extend(find_non_content_images(value))
            # Do not scan arbitrary string fields for [img:] here to avoid duplicating inline images

    elif isinstance(data, list):
        for item in data:
            images.extend(find_non_content_images(item))
            
    # Return unique images
    unique_images = []
    seen = set()
    for img in images:
        rep = tuple(sorted(img.items()))
        if rep not in seen:
            unique_images.append(img)
            seen.add(rep)
    return unique_images


def download_image(image_info, images_json_dir, downloaded_images_dir):
    """Downloads an image either from a URL or by ID and returns the local path."""
    image_url = None
    if 'url' in image_info:
        image_url = image_info['url']
    elif 'id' in image_info:
        image_id = image_info['id']
        image_json_files = [f for f in os.listdir(images_json_dir) if f.endswith(f"-{image_id}.json")]
        if not image_json_files:
            print(f"Warning: No JSON file found for image ID {image_id}")
            return None
        
        image_json_path = os.path.join(images_json_dir, image_json_files[0])
        try:
            with open(image_json_path, 'r', encoding='utf-8') as f:
                image_data = json.load(f)
            image_url = image_data.get("url")
        except Exception as e:
            print(f"Error reading image JSON for ID {image_id}: {e}")
            return None
    
    if not image_url:
        print(f"Warning: No URL found for image info: {image_info}")
        return None

    if not os.path.exists(downloaded_images_dir):
        os.makedirs(downloaded_images_dir)

    try:
        image_filename = os.path.basename(image_url.split('?')[0])
        local_image_path = os.path.join(downloaded_images_dir, image_filename)

        if not os.path.exists(local_image_path):
            print(f"Downloading image: {image_url}")
            response = requests.get(image_url, stream=True)
            response.raise_for_status()
            with open(local_image_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)
        
        # Handle WebP conversion
        if local_image_path.lower().endswith('.webp'):
            png_path = os.path.splitext(local_image_path)[0] + '.png'
            if not os.path.exists(png_path):
                print(f"Converting {local_image_path} to PNG...")
                with Image.open(local_image_path) as img:
                    img.save(png_path, 'PNG')
            return png_path

        return local_image_path
    except Exception as e:
        print(f"Error downloading image from {image_url}: {e}")
        return None


def clean_world_anvil_text(text):
    """Cleans text from World Anvil, removing special tags, UUIDs, and BBCode-style tags."""
    # Pattern to find World Anvil tags like @[person:uuid](Display Name)
    # and replace them with "Display Name".
    pattern = r'@\[[a-zA-Z0-9_\-]+:[0-9a-fA-F\-]+\]\((.*?)\)'
    cleaned_text = re.sub(pattern, r'\1', text)

    # Pattern for article references like @[The Core Realms](Article:)
    article_ref_pattern = r'@\[(.*?)\]\(Article:[^)]*\)'
    cleaned_text = re.sub(article_ref_pattern, r'\1', cleaned_text)

    # Pattern for tags without display text, like @[person:uuid]
    pattern_no_display = r'@\[[a-zA-Z0-9_\-]+:[0-9a-fA-F\-]+\]'
    cleaned_text = re.sub(pattern_no_display, '', cleaned_text)

    # Pattern for standalone UUIDs
    uuid_pattern = r'[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}'
    cleaned_text = re.sub(uuid_pattern, '', cleaned_text)

    # NOTE: We do NOT remove image tags here, as they are used for splitting the content.
    # image_tag_pattern = r'\[img:[0-9]+(?:\|[^\]]+)*\]'
    # cleaned_text = re.sub(image_tag_pattern, '', cleaned_text)

    # Pattern for BBCode-style tags like [p], [/p], [b], [/b], and [h2|...], [url:...]
    bbcode_pattern = r'\[/?\w+(?:\|[^\]]*)?\]|\[url:[^\]]+\]'
    cleaned_text = re.sub(bbcode_pattern, '', cleaned_text)

    # Clean up excessive newlines and surrounding whitespace
    cleaned_text = re.sub(r'[\t ]+', ' ', cleaned_text)
    cleaned_text = re.sub(r'\n\s*\n', '\n\n', cleaned_text)
    cleaned_text = cleaned_text.strip()
    return cleaned_text


def extract_article_sections(article_data):
    """Return an ordered list of sections from the article.

    Each section is a dict: { 'heading': Optional[str], 'key': str, 'text': str }
    - The main 'content' appears first with heading=None.
    - Other content-like fields (e.g., demographics, history, industry, architecture, pointOfInterest, etc.)
      are included as their own sections with a friendly heading derived from the field name.
    """
    if not isinstance(article_data, dict):
        return []

    # Keys we know are metadata or non-body content to skip
    exclude_keys = {
        'id','title','slug','state','isWip','isDraft','entityClass','icon','url','subscribergroups',
        'folderId','tags','updateDate','position','excerpt','wordcount','creationDate','publicationDate',
        'notificationDate','likes','views','userMetadata','articleMetadata','cssClasses','displayCss',
        'templateType','customArticleTemplate','editor','author','category','world','cover','coverSource',
        'pronunciation','snippet','seeded','sidebarcontent','sidepanelcontenttop','sidepanelcontent',
        'sidebarcontentbottom','footnotes','fullfooter','authornotes','scrapbook','credits','displaySidebar',
        'articleNext','articlePrevious','timeline','prompt','gallery','articleParent','block','orgchart',
        'showSeeded','webhookUpdate','communityUpdate','commentPlaceholder','passcodecta','metaTitle',
        'metaDescription','subheading','coverIsMap','isFeaturedArticle','isAdultContent','isLocked',
        'allowComments','allowContentCopy','showInToc','isEmphasized','displayAuthor','displayChildrenUnder',
        'displayTitle','displaySheet','badge','editURL','success','isEditable'
    }

    # Friendly name overrides for specific keys
    friendly_map = {
        'pointOfInterest': 'Point of Interest',
        'agricultureAndIndustry': 'Agriculture and Industry',
        'tradeAndTransport': 'Trade and Transport',
        'publicAgenda': 'Public Agenda',
        'alternativeNames': 'Alternative Names',
        'geographicLocation': 'Geographic Location',
        'foreignrelations': 'Foreign Relations',
        'economicsystem': 'Economic System',
        'governmentsystem': 'Government System'
    }

    def friendly_title(key: str) -> str:
        if key in friendly_map:
            return friendly_map[key]
        # Insert spaces before capitals in camelCase and title-case it
        spaced = re.sub(r'(?<!^)(?=[A-Z])', ' ', key)
        # Replace common separators
        spaced = spaced.replace('_', ' ').replace('-', ' ')
        return spaced[:1].upper() + spaced[1:]

    sections = []

    # Primary content first
    primary = article_data.get('content')
    if isinstance(primary, str) and primary.strip():
        sections.append({'heading': None, 'key': 'content', 'text': primary})

    # Consider any other string fields that look like content
    for key, value in article_data.items():
        if key == 'content' or key in exclude_keys:
            continue
        if isinstance(value, str):
            v = value.strip()
            if not v:
                continue
            # Looks like WA body if it has BBCode-like tags or HTML or is sufficiently long
            if re.search(r'\[(?:/)?\w+(?:\|[^\]]*)?\]|<[^>]+>|\n', v) or len(v) > 80:
                sections.append({'heading': friendly_title(key), 'key': key, 'text': v})

    return sections

def write_heading(pdf: FPDF, level: int, text: str):
    """Write a heading with size based on level (1-6). Avoid bold to keep single TTF dependency."""
    sizes = {1: 18, 2: 14, 3: 12, 4: 11, 5: 10, 6: 10}
    size = sizes.get(level, 12)
    pdf.ln(2)
    pdf.set_font('DejaVu', '', size)
    # Ensure no BBCode remnants like [b][/b]
    text = clean_world_anvil_text(text)
    pdf.multi_cell(0, 7, text.strip(), align='L')
    pdf.ln(1)

def process_content_stream(pdf: FPDF, text: str, images_json_dir: str | None = None, downloaded_images_dir: str | None = None):
    """Process WA content text: render headings [h1-h6], tables, images, and paragraphs with cleaning."""
    if not text or not text.strip():
        return

    # Unescape HTML entities and strip HTML tags
    raw_text = unescape(text)
    html_tag_pattern = r'<[^>]+>'
    stream = re.sub(html_tag_pattern, '', raw_text)

    # Combined regex to iterate tokens
    pattern = re.compile(
        r'(?P<table>\[table\][\s\S]*?\[/table\])'
        r'|(?P<img>\[img:[0-9]+(?:\|[^\]]+)*\])'
        r'|(?P<heading>\[(?P<h_tag>h[1-6])(?:\|[^\]]*)?\](?P<h_text>[\s\S]*?)\[/(?P=h_tag)\])',
        flags=re.IGNORECASE | re.DOTALL
    )

    pos = 0
    for m in pattern.finditer(stream):
        # Text before this token
        if m.start() > pos:
            chunk = stream[pos:m.start()]
            clean_text = clean_world_anvil_text(chunk)
            if clean_text:
                pdf.set_font('DejaVu', '', 10)
                pdf.multi_cell(0, 6, clean_text, align='L')

        if m.group('table'):
            rows, is_header = parse_wa_table(m.group('table'))
            render_table(pdf, rows, is_header)
        elif m.group('img'):
            if images_json_dir and downloaded_images_dir:
                image_id_match = re.search(r'\[img:([0-9]+)', m.group('img'))
                if image_id_match:
                    image_id = image_id_match.group(1)
                    local_image_path = download_image({'id': image_id}, images_json_dir, downloaded_images_dir)
                    if local_image_path:
                        add_scaled_image(pdf, local_image_path, max_page_height_ratio=0.5)
        elif m.group('heading'):
            tag = m.group('h_tag')  # h1..h6
            heading_text = m.group('h_text') or ''
            level = int(tag[1]) if len(tag) >= 2 and tag[1].isdigit() else 2
            write_heading(pdf, level, heading_text)

        pos = m.end()

    # Trailing text
    if pos < len(stream):
        chunk = stream[pos:]
        clean_text = clean_world_anvil_text(chunk)
        if clean_text:
            pdf.set_font('DejaVu', '', 10)
            pdf.multi_cell(0, 6, clean_text, align='L')


def add_scaled_image(pdf, image_path, max_page_height_ratio=0.5):
    """Place an image aligned to the left margin, scaled to page width within margins,
    and limited to a fraction of the usable page height. Advances the cursor below the image.

    Args:
        pdf (FPDF): The FPDF instance.
        image_path (str): Local path to the image.
        max_page_height_ratio (float): Maximum fraction of usable page height the image may occupy.
    """
    try:
        with Image.open(image_path) as img:
            width, height = img.size

        # Compute available width within margins
        page_width = pdf.w - pdf.l_margin - getattr(pdf, 'r_margin', pdf.l_margin)

        # Initial scale to fit width
        ratio = page_width / width if width else 1.0
        new_width = page_width
        new_height = height * ratio if height else 0

        # Limit height to a portion of the usable page height
        usable_page_height = pdf.h - getattr(pdf, 't_margin', 0) - getattr(pdf, 'b_margin', 0)
        max_height = usable_page_height * max_page_height_ratio
        if new_height > max_height and height:
            scale = max_height / new_height
            new_height = max_height
            new_width = new_width * scale

        # If after height limiting we still exceed width (edge numerical case), clamp to width
        if new_width > page_width:
            scale = page_width / new_width
            new_width *= scale
            new_height *= scale

        # Ensure the image doesn't overflow the bottom; add a page if needed
        cur_y = pdf.get_y()
        bottom_limit = pdf.h - getattr(pdf, 'b_margin', 0)
        if cur_y + new_height > bottom_limit:
            pdf.add_page()
            cur_y = pdf.get_y()

        # Place image at left margin and current Y
        x = pdf.l_margin
        pdf.image(image_path, x=x, y=cur_y, w=new_width, h=new_height)

        # Move cursor below the image with a small gap
        pdf.set_xy(pdf.l_margin, cur_y + new_height + 3)
    except Exception as e:
        print(f"Error adding image {image_path} to PDF: {e}")


def create_pdf_summary(json_data: list, output_filename: str = "world_anvil_summary.pdf", images_json_dir: str | None = None, downloaded_images_dir: str | None = None, font_path: str | None = None):
    """
    Creates a PDF summary from the combined World Anvil JSON data.
    Extracts and cleans title and content from each article, and adds images.
    """
    pdf = FPDF()
    
    # Resolve font path
    font_filename = "DejaVuSans.ttf"
    script_dir = os.path.dirname(os.path.abspath(__file__))
    # When running as a PyInstaller bundle, bundled data files are in sys._MEIPASS
    bundle_dir = getattr(sys, '_MEIPASS', None)
    resolved_font = None

    if font_path:
        if os.path.exists(font_path):
            resolved_font = os.path.abspath(font_path)
        else:
            print(f"Error: Specified font file '{font_path}' not found.")
            return
    else:
        candidates = [
            os.path.join(script_dir, font_filename),
            os.path.join(os.getcwd(), font_filename),
        ]
        if bundle_dir:
            candidates.insert(0, os.path.join(bundle_dir, font_filename))
        for candidate in candidates:
            if os.path.exists(candidate):
                resolved_font = os.path.abspath(candidate)
                break

    if not resolved_font:
        print(f"Error: Font file '{font_filename}' not found.")
        print(f"  Checked: {os.path.join(script_dir, font_filename)}")
        print(f"           {os.path.join(os.getcwd(), font_filename)}")
        print(f"  Use --font to specify the path to a .ttf font file.")
        return

    try:
        pdf.add_font('DejaVu', '', resolved_font, uni=True)
    except TypeError:
        # uni parameter removed in newer fpdf2 versions
        pdf.add_font('DejaVu', '', resolved_font)
    except Exception as e:
        print(f"Error: Could not load font '{resolved_font}': {e}")
        return

    pdf.set_font('DejaVu', '', 12)
    # Ensure automatic page breaks with a reasonable bottom margin
    try:
        pdf.set_auto_page_break(auto=True, margin=max(12, getattr(pdf, 'b_margin', 12)))
    except Exception:
        # Some FPDF variants may not expose setter; safe to continue.
        pass

    total_articles = len(json_data)
    processed = 0
    for article_data in json_data:
        if not isinstance(article_data, dict):
            continue

        title = article_data.get("title", "No Title")
        title = clean_world_anvil_text(title)
        processed += 1
        print(f"  [{processed}/{total_articles}] {title}")
        sections = extract_article_sections(article_data)
        # Only include articles with at least one non-empty section
        if not sections:
            continue

        pdf.add_page()
        
        # Add title
        pdf.set_font('DejaVu', '', 16)
        
        # Check for Secret status and add right-aligned label
        if article_data.get("entityClass") == "Secret":
            # Save current position
            x_start = pdf.get_x()
            y_start = pdf.get_y()
            
            # Move to right and print (SECRET)
            # We use cell with ln=0 to not move cursor to next line automatically, 
            # but we want it right aligned. 
            # FPDF cell: w=0 means goes to right margin. align='R' aligns text to right.
            pdf.cell(0, 8, "(SECRET)", align='R', ln=0)
            
            # Reset cursor to start of line for the title
            pdf.set_xy(x_start, y_start)

        pdf.multi_cell(0, 8, title, align='L')
        pdf.ln(4)

        # Add non-content images (like portraits) at the top
        if images_json_dir and downloaded_images_dir:
            non_content_images = find_non_content_images(article_data)
            for image_info in non_content_images:
                local_image_path = download_image(image_info, images_json_dir, downloaded_images_dir)
                if local_image_path:
                    add_scaled_image(pdf, local_image_path, max_page_height_ratio=0.5)

        # Render sections: main content first (no heading), then alternative fields as section headings
        for sec in sections:
            if sec.get('heading'):
                # Use H2 for section headings beneath the article title
                write_heading(pdf, 2, sec['heading'])
            process_content_stream(pdf, sec.get('text', ''), images_json_dir, downloaded_images_dir)

    try:
        pdf.output(output_filename)
        print(f"\nSuccessfully created PDF summary: {output_filename}")
    except Exception as e:
        print(f"Error creating PDF: {e}")


def combine_json_files(file_paths, output_filename="combined_world_anvil_data.json"):
    """
    Combines multiple JSON files into a single JSON array.

    Args:
        file_paths (list): A list of paths to the JSON files to be combined.
        output_filename (str): The name of the output file.
    """
    combined_data = []
    errors = 0

    for file_path in file_paths:
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                combined_data.append(data)
        except FileNotFoundError:
            print(f"  Warning: File not found: {file_path}")
            errors += 1
        except json.JSONDecodeError:
            print(f"  Warning: Invalid JSON in {os.path.basename(file_path)}")
            errors += 1
        except Exception as e:
            print(f"  Warning: Error reading {os.path.basename(file_path)}: {e}")
            errors += 1

    try:
        with open(output_filename, 'w', encoding='utf-8') as f:
            json.dump(combined_data, f, indent=4)
        msg = f"Loaded {len(combined_data)} files."
        if errors:
            msg += f" ({errors} skipped due to errors)"
        print(msg)
        return combined_data
    except Exception as e:
        print(f"Error writing combined data to {output_filename}: {e}")
        return None

def find_world_root(extract_dir):
    """Find the inner world directory containing 'articles/' within an extracted export.

    World Anvil exports have the structure:
        World-Name-YYYY-MM-DD/
            World-Name-xxx/
                articles/
                secrets/
                images/
                ...

    This function walks down to find the directory that directly contains 'articles/'.
    """
    # Check if extract_dir itself contains articles/
    if os.path.isdir(os.path.join(extract_dir, "articles")):
        return extract_dir

    # Otherwise look one or two levels deep
    for root, dirs, _files in os.walk(extract_dir):
        if "articles" in dirs:
            return root

    return None


def find_latest_export(input_dir):
    """Find and extract the most recent World Anvil export ZIP in input_dir.

    Looks for ZIP files whose names contain a YYYY-MM-DD date and selects the
    most recent one. The ZIP is extracted into input_dir if not already extracted.

    Returns the path to the inner world root directory, or None.
    """
    if not os.path.isdir(input_dir):
        print(f"Error: Input directory '{input_dir}' does not exist.")
        return None

    date_pattern = re.compile(r'(\d{4}-\d{2}-\d{2})')

    # Collect ZIPs with parseable dates
    zip_candidates = []
    for f in os.listdir(input_dir):
        if not f.lower().endswith('.zip'):
            continue
        m = date_pattern.search(f)
        if m:
            zip_candidates.append((m.group(1), f))

    # Also consider already-extracted directories
    dir_candidates = []
    for d in os.listdir(input_dir):
        full = os.path.join(input_dir, d)
        if not os.path.isdir(full):
            continue
        m = date_pattern.search(d)
        if m:
            dir_candidates.append((m.group(1), full))

    if not zip_candidates and not dir_candidates:
        print(f"No World Anvil export ZIPs or folders found in '{input_dir}'.")
        print("Place a World Anvil export ZIP (e.g. World-MyWorld-2025-01-15.zip) in the input/ folder.")
        return None

    # Pick the newest ZIP and extract if needed
    if zip_candidates:
        zip_candidates.sort(key=lambda x: x[0], reverse=True)
        _best_date, best_zip = zip_candidates[0]
        zip_path = os.path.join(input_dir, best_zip)
        extract_name = os.path.splitext(best_zip)[0]
        extract_path = os.path.join(input_dir, extract_name)

        if not os.path.isdir(extract_path):
            print(f"Extracting {best_zip}...")
            with zipfile.ZipFile(zip_path, 'r') as zf:
                zf.extractall(extract_path)
            print(f"Extracted to {extract_path}")

        world_root = find_world_root(extract_path)
        if world_root:
            return world_root

    # Fall back to already-extracted directories
    if dir_candidates:
        dir_candidates.sort(key=lambda x: x[0], reverse=True)
        for _date, dir_path in dir_candidates:
            world_root = find_world_root(dir_path)
            if world_root:
                return world_root

    print("Could not locate articles/ directory within the export. Check the export structure.")
    return None


def collect_json_files(dir_path):
    """Return a list of .json file paths from dir_path, or empty list if missing."""
    if not os.path.isdir(dir_path):
        return []
    return [os.path.join(dir_path, f) for f in os.listdir(dir_path) if f.endswith('.json')]


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Convert World Anvil exports into a readable PDF document.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="Examples:\n"
               "  python wa_to_pdf.py\n"
               "  python wa_to_pdf.py --input ./my_exports --output ./pdfs\n"
               "  python wa_to_pdf.py --font /path/to/MyFont.ttf\n"
               "  python wa_to_pdf.py --no-secrets",
    )
    parser.add_argument(
        "-i", "--input", dest="input_dir",
        help="Input directory containing export ZIPs or folders (default: input/ next to script)",
    )
    parser.add_argument(
        "-o", "--output", dest="output_dir",
        help="Output directory for generated PDF (default: output/ next to script)",
    )
    parser.add_argument(
        "-c", "--cache", dest="cache_dir",
        help="Cache directory for downloaded images (default: cache/ next to script)",
    )
    parser.add_argument(
        "-f", "--font", dest="font_path",
        help="Path to a .ttf font file (default: DejaVuSans.ttf next to script)",
    )
    parser.add_argument(
        "--no-secrets", action="store_true",
        help="Exclude secret articles from the PDF",
    )
    args = parser.parse_args(argv)

    # When running as a PyInstaller bundle, use the exe's directory (not the temp extraction dir)
    if getattr(sys, '_MEIPASS', None):
        script_dir = os.path.dirname(sys.executable)
        atexit.register(lambda: input("Press Enter to exit..."))
    else:
        script_dir = os.path.dirname(os.path.abspath(__file__))
    input_dir = args.input_dir if args.input_dir else os.path.join(script_dir, "input")
    output_dir = args.output_dir if args.output_dir else os.path.join(script_dir, "output")
    cache_dir = args.cache_dir if args.cache_dir else os.path.join(script_dir, "cache")

    os.makedirs(input_dir, exist_ok=True)
    os.makedirs(output_dir, exist_ok=True)

    world_anvil_root_dir = find_latest_export(input_dir)

    if not world_anvil_root_dir:
        sys.exit(1)

    print(f"Using export: {world_anvil_root_dir}")

    json_articles_dir = os.path.join(world_anvil_root_dir, "articles")
    json_secrets_dir = os.path.join(world_anvil_root_dir, "secrets")
    images_json_dir = os.path.join(world_anvil_root_dir, "images")

    # Cache downloaded images per world so re-runs don't re-download
    world_name = os.path.basename(world_anvil_root_dir)
    downloaded_images_dir = os.path.join(cache_dir, world_name)
    os.makedirs(downloaded_images_dir, exist_ok=True)

    output_filename = os.path.join(output_dir, "combined_world_anvil_data.json")
    output_pdf_filename = os.path.join(output_dir, "world_anvil_summary.pdf")

    article_files = collect_json_files(json_articles_dir)
    secret_files = [] if args.no_secrets else collect_json_files(json_secrets_dir)
    json_files_to_combine = article_files + secret_files

    print(f"Found {len(article_files)} articles and {len(secret_files)} secrets.")

    if not json_files_to_combine:
        sys.exit(
            f"Error: No JSON files found under '{world_anvil_root_dir}'.\n"
            "Ensure the export contains 'articles' or 'secrets' directories with .json files."
        )

    combined_data = combine_json_files(json_files_to_combine, output_filename)

    if combined_data:
        create_pdf_summary(
            combined_data, output_pdf_filename, images_json_dir,
            downloaded_images_dir, font_path=args.font_path,
        )

    # Clean up intermediate file
    if os.path.exists(output_filename):
        os.remove(output_filename)


if __name__ == "__main__":
    main()
