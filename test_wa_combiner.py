"""Tests for wa_combiner.py"""

import json
import os
import pytest

from wa_combiner import (
    parse_wa_table,
    clean_world_anvil_text,
    extract_article_sections,
    find_non_content_images,
    find_world_root,
    collect_json_files,
    combine_json_files,
)


class TestParseWaTable:
    def test_simple_table_with_header(self):
        table_text = "[table][tr][th]Name[/th][th]Value[/th][/tr][tr][td]Foo[/td][td]Bar[/td][/tr][/table]"
        rows, is_header = parse_wa_table(table_text)
        assert is_header is True
        assert rows == [["Name", "Value"], ["Foo", "Bar"]]

    def test_no_header(self):
        table_text = "[table][tr][td]A[/td][td]B[/td][/tr][tr][td]C[/td][td]D[/td][/tr][/table]"
        rows, is_header = parse_wa_table(table_text)
        assert is_header is False
        assert rows == [["A", "B"], ["C", "D"]]

    def test_empty_table(self):
        table_text = "[table][/table]"
        rows, is_header = parse_wa_table(table_text)
        assert rows == []
        assert is_header is False

    def test_single_row_single_cell(self):
        table_text = "[table][tr][td]Only Cell[/td][/tr][/table]"
        rows, is_header = parse_wa_table(table_text)
        assert rows == [["Only Cell"]]
        assert is_header is False

    def test_case_insensitive_tags(self):
        table_text = "[TABLE][TR][TH]Header[/TH][/TR][TR][TD]Data[/TD][/TR][/TABLE]"
        rows, is_header = parse_wa_table(table_text)
        assert is_header is True
        assert rows == [["Header"], ["Data"]]

    def test_multiple_header_columns(self):
        table_text = "[table][tr][th]A[/th][th]B[/th][th]C[/th][/tr][/table]"
        rows, is_header = parse_wa_table(table_text)
        assert is_header is True
        assert rows == [["A", "B", "C"]]

    def test_whitespace_in_cells(self):
        table_text = "[table][tr][td]  hello  [/td][td]  world  [/td][/tr][/table]"
        rows, is_header = parse_wa_table(table_text)
        assert rows == [["hello", "world"]]


class TestCleanWorldAnvilText:
    def test_person_reference_with_display_name(self):
        text = "@[person:12345678-1234-1234-1234-123456789abc](John Doe)"
        assert clean_world_anvil_text(text) == "John Doe"

    def test_article_reference(self):
        text = "@[The Core Realms](Article:)"
        assert clean_world_anvil_text(text) == "The Core Realms"

    def test_article_reference_with_id(self):
        text = "@[Some Place](Article:12345678-1234-1234-1234-123456789abc)"
        assert clean_world_anvil_text(text) == "Some Place"

    def test_standalone_uuid_removed(self):
        text = "Some text 12345678-1234-1234-1234-123456789abc more text"
        result = clean_world_anvil_text(text)
        assert "12345678" not in result
        assert "Some text" in result
        assert "more text" in result

    def test_bbcode_tags_stripped(self):
        text = "[p]Hello[/p] [b]world[/b]"
        assert clean_world_anvil_text(text) == "Hello world"

    def test_url_tags_stripped(self):
        text = "[url:https://example.com]Click here"
        assert clean_world_anvil_text(text) == "Click here"

    def test_excessive_whitespace_collapsed(self):
        text = "Hello   \t  world"
        result = clean_world_anvil_text(text)
        assert result == "Hello world"

    def test_excessive_newlines_collapsed(self):
        text = "Hello\n\n\n\nworld"
        result = clean_world_anvil_text(text)
        assert result == "Hello\n\nworld"

    def test_empty_string(self):
        assert clean_world_anvil_text("") == ""

    def test_plain_text_unchanged(self):
        text = "Just a normal sentence."
        assert clean_world_anvil_text(text) == "Just a normal sentence."

    def test_reference_without_display_text(self):
        text = "Hello @[person:12345678-1234-1234-1234-123456789abc] world"
        result = clean_world_anvil_text(text)
        assert "person" not in result
        assert "12345678" not in result

    def test_heading_tags_with_pipe(self):
        text = "[h2|anchor]Title Text[/h2]"
        result = clean_world_anvil_text(text)
        assert result == "Title Text"

    def test_multiple_references_in_one_text(self):
        text = "@[person:aaaa1111-2222-3333-4444-555566667777](Alice) met @[person:bbbb1111-2222-3333-4444-555566667777](Bob)"
        result = clean_world_anvil_text(text)
        assert result == "Alice met Bob"


class TestExtractArticleSections:
    def test_content_only(self):
        article = {"title": "Test", "content": "[p]Hello world[/p]"}
        sections = extract_article_sections(article)
        assert len(sections) == 1
        assert sections[0]["key"] == "content"
        assert sections[0]["heading"] is None

    def test_additional_long_field(self):
        article = {
            "title": "Test City",
            "content": "Main content here.",
            "demographics": "Population: 5000\nRaces: Human, Elf, Dwarf",
        }
        sections = extract_article_sections(article)
        assert len(sections) == 2
        assert sections[0]["key"] == "content"
        assert sections[1]["key"] == "demographics"
        assert sections[1]["heading"] == "Demographics"

    def test_excludes_metadata_keys(self):
        article = {
            "title": "Test",
            "content": "Body text.",
            "id": "12345",
            "slug": "test-article",
            "state": "public",
            "tags": "fantasy",
        }
        sections = extract_article_sections(article)
        assert len(sections) == 1
        assert sections[0]["key"] == "content"

    def test_no_content_returns_empty(self):
        article = {"title": "Empty", "id": "123"}
        sections = extract_article_sections(article)
        assert sections == []

    def test_non_dict_input_returns_empty(self):
        assert extract_article_sections("not a dict") == []
        assert extract_article_sections(42) == []
        assert extract_article_sections(None) == []

    def test_friendly_name_for_camelcase(self):
        article = {
            "title": "Test",
            "pointOfInterest": "The big fountain in the town square is quite remarkable indeed and draws visitors from far and wide.",
        }
        sections = extract_article_sections(article)
        assert any(s["heading"] == "Point of Interest" for s in sections)

    def test_short_strings_excluded(self):
        """Short strings without BBCode or newlines are excluded."""
        article = {
            "title": "Test",
            "content": "Main body text with enough content.",
            "someField": "short",
        }
        sections = extract_article_sections(article)
        assert all(s["key"] != "someField" for s in sections)

    def test_bbcode_field_included(self):
        """Fields with BBCode tags are included even if short."""
        article = {
            "title": "Test",
            "history": "[p]Founded long ago[/p]",
        }
        sections = extract_article_sections(article)
        assert any(s["key"] == "history" for s in sections)

    def test_empty_content_skipped(self):
        article = {"title": "Test", "content": "   "}
        sections = extract_article_sections(article)
        assert sections == []


class TestFindNonContentImages:
    def test_portrait_image(self):
        data = {"portrait": {"url": "https://example.com/portrait.jpg"}}
        images = find_non_content_images(data)
        assert len(images) == 1
        assert images[0]["url"] == "https://example.com/portrait.jpg"

    def test_cover_image(self):
        data = {"cover": {"url": "https://example.com/cover.jpg", "title": "My Cover"}}
        images = find_non_content_images(data)
        assert len(images) == 1

    def test_default_cover_excluded(self):
        data = {"cover": {"url": "https://example.com/cover.jpg", "title": "Default Cover Image"}}
        images = find_non_content_images(data)
        assert len(images) == 0

    def test_skips_content_field(self):
        data = {
            "content": {"portrait": {"url": "https://example.com/hidden.jpg"}},
            "portrait": {"url": "https://example.com/visible.jpg"},
        }
        images = find_non_content_images(data)
        assert len(images) == 1
        assert images[0]["url"] == "https://example.com/visible.jpg"

    def test_nested_data(self):
        data = {
            "metadata": {
                "portrait": {"url": "https://example.com/nested.jpg"}
            }
        }
        images = find_non_content_images(data)
        assert len(images) == 1

    def test_deduplication(self):
        data = [
            {"portrait": {"url": "https://example.com/same.jpg"}},
            {"portrait": {"url": "https://example.com/same.jpg"}},
        ]
        images = find_non_content_images(data)
        assert len(images) == 1

    def test_empty_data(self):
        assert find_non_content_images({}) == []
        assert find_non_content_images([]) == []

    def test_portrait_and_cover_together(self):
        data = {
            "portrait": {"url": "https://example.com/portrait.jpg"},
            "cover": {"url": "https://example.com/cover.jpg", "title": "Custom Cover"},
        }
        images = find_non_content_images(data)
        assert len(images) == 2


class TestFindWorldRoot:
    def test_direct_articles_dir(self, tmp_path):
        (tmp_path / "articles").mkdir()
        assert find_world_root(str(tmp_path)) == str(tmp_path)

    def test_nested_articles_dir(self, tmp_path):
        inner = tmp_path / "World-Name-123"
        (inner / "articles").mkdir(parents=True)
        result = find_world_root(str(tmp_path))
        assert result == str(inner)

    def test_no_articles_dir(self, tmp_path):
        (tmp_path / "other_folder").mkdir()
        assert find_world_root(str(tmp_path)) is None

    def test_deeply_nested(self, tmp_path):
        deep = tmp_path / "level1" / "level2"
        (deep / "articles").mkdir(parents=True)
        result = find_world_root(str(tmp_path))
        assert result == str(deep)

    def test_with_sibling_dirs(self, tmp_path):
        (tmp_path / "articles").mkdir()
        (tmp_path / "secrets").mkdir()
        (tmp_path / "images").mkdir()
        assert find_world_root(str(tmp_path)) == str(tmp_path)


class TestCollectJsonFiles:
    def test_finds_json_files(self, tmp_path):
        (tmp_path / "a.json").write_text("{}")
        (tmp_path / "b.json").write_text("{}")
        (tmp_path / "c.txt").write_text("not json")
        files = collect_json_files(str(tmp_path))
        assert len(files) == 2
        assert all(f.endswith(".json") for f in files)

    def test_missing_directory(self):
        files = collect_json_files("/nonexistent/path/that/does/not/exist")
        assert files == []

    def test_empty_directory(self, tmp_path):
        files = collect_json_files(str(tmp_path))
        assert files == []

    def test_ignores_subdirectories(self, tmp_path):
        (tmp_path / "a.json").write_text("{}")
        sub = tmp_path / "subdir"
        sub.mkdir()
        (sub / "b.json").write_text("{}")
        files = collect_json_files(str(tmp_path))
        assert len(files) == 1


class TestCombineJsonFiles:
    def test_combines_multiple_files(self, tmp_path):
        f1 = tmp_path / "a.json"
        f2 = tmp_path / "b.json"
        f1.write_text(json.dumps({"title": "Article A"}))
        f2.write_text(json.dumps({"title": "Article B"}))
        output = tmp_path / "combined.json"

        result = combine_json_files([str(f1), str(f2)], str(output))
        assert result is not None
        assert len(result) == 2
        assert result[0]["title"] == "Article A"
        assert result[1]["title"] == "Article B"
        assert output.exists()

    def test_handles_missing_file(self, tmp_path):
        f1 = tmp_path / "a.json"
        f1.write_text(json.dumps({"title": "A"}))
        output = tmp_path / "combined.json"

        result = combine_json_files([str(f1), "/nonexistent/file.json"], str(output))
        assert result is not None
        assert len(result) == 1

    def test_handles_invalid_json(self, tmp_path):
        f1 = tmp_path / "bad.json"
        f1.write_text("not valid json {{{")
        output = tmp_path / "combined.json"

        result = combine_json_files([str(f1)], str(output))
        assert result is not None
        assert len(result) == 0

    def test_empty_file_list(self, tmp_path):
        output = tmp_path / "combined.json"
        result = combine_json_files([], str(output))
        assert result is not None
        assert len(result) == 0

    def test_output_is_valid_json(self, tmp_path):
        f1 = tmp_path / "a.json"
        f1.write_text(json.dumps({"title": "Test"}))
        output = tmp_path / "combined.json"

        combine_json_files([str(f1)], str(output))
        with open(str(output), 'r') as f:
            data = json.load(f)
        assert isinstance(data, list)
        assert len(data) == 1
