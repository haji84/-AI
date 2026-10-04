from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
from html.parser import HTMLParser
import re
import xml.etree.ElementTree as ET


PARSER_VERSION = "legal-structure-v1"

STRUCTURAL_XML_TYPES = {
    "Preamble": "preamble",
    "Part": "part",
    "Chapter": "chapter",
    "Section": "section",
    "Subsection": "subsection",
    "Division": "division",
    "Article": "article",
    "Paragraph": "paragraph",
    "Item": "item",
    "Subitem1": "subitem1",
    "Subitem2": "subitem2",
    "Subitem3": "subitem3",
    "Subitem4": "subitem4",
    "Subitem5": "subitem5",
    "Subitem6": "subitem6",
    "Subitem7": "subitem7",
    "Subitem8": "subitem8",
    "Subitem9": "subitem9",
    "Subitem10": "subitem10",
    "SupplProvision": "supplementary",
    "Appdx": "appendix",
    "AppdxTable": "appendix_table",
    "AppdxStyle": "form",
    "AppdxFig": "appendix_figure",
    "AppdxNote": "appendix_note",
}

LABEL_TAGS = {
    "Part": ["PartTitle"],
    "Chapter": ["ChapterTitle"],
    "Section": ["SectionTitle"],
    "Subsection": ["SubsectionTitle"],
    "Division": ["DivisionTitle"],
    "Article": ["ArticleTitle"],
    "Paragraph": ["ParagraphNum"],
    "Item": ["ItemTitle"],
    "Subitem1": ["Subitem1Title"],
    "Subitem2": ["Subitem2Title"],
    "Subitem3": ["Subitem3Title"],
    "Subitem4": ["Subitem4Title"],
    "Subitem5": ["Subitem5Title"],
    "Subitem6": ["Subitem6Title"],
    "Subitem7": ["Subitem7Title"],
    "Subitem8": ["Subitem8Title"],
    "Subitem9": ["Subitem9Title"],
    "Subitem10": ["Subitem10Title"],
    "SupplProvision": ["SupplProvisionLabel"],
    "Appdx": ["AppdxTitle"],
    "AppdxTable": ["AppdxTableTitle"],
    "AppdxStyle": ["AppdxStyleTitle"],
    "AppdxFig": ["AppdxFigTitle"],
    "AppdxNote": ["AppdxNoteTitle"],
}

HEADING_TAGS = {
    "Article": ["ArticleCaption"],
    "Paragraph": ["ParagraphCaption"],
}

ARTICLE_RE = re.compile(r"^第\s*([一二三四五六七八九十百千〇零0-9０-９のノ]+)\s*条(?:\s*の\s*([0-9０-９一二三四五六七八九十]+))?")
PARAGRAPH_RE = re.compile(r"^[（(]?\s*([0-9０-９]+)\s*[）)]?\s*(.*)$")
ITEM_RE = re.compile(r"^([一二三四五六七八九十百]+|[イロハニホヘトチリヌルヲワカヨタレソツネナラムウヰノオクヤマケフコエテアサキユメミシヱヒモセス])(?:[\s　]+|[、．.])(.+)$")
SUPPL_RE = re.compile(r"^附\s*則")
APPENDIX_RE = re.compile(r"^(別表|別記|様式|別紙|付表|附表)\s*([第0-9０-９一二三四五六七八九十百号]*)")


@dataclass
class ProvisionRecord:
    provision_key: str
    parent_key: str | None
    provision_type: str
    sequence_no: int
    display_label: str | None = None
    heading_text: str | None = None
    body_text: str = ""
    source_anchor: str | None = None
    source_path: str | None = None
    source_meta: dict = field(default_factory=dict)

    @property
    def content_sha256(self) -> str:
        payload = "\n".join(
            [
                self.provision_type,
                self.display_label or "",
                self.heading_text or "",
                self.body_text or "",
            ]
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _lname(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _norm(text: str | None) -> str:
    if not text:
        return ""
    return re.sub(r"[\s　]+", " ", text).strip()


def _iter_text(node: ET.Element) -> str:
    return _norm("".join(node.itertext()))


def _first_child_text(node: ET.Element, names: list[str]) -> str | None:
    wanted = set(names)
    for child in node:
        if _lname(child.tag) in wanted:
            value = _iter_text(child)
            if value:
                return value
    return None


def _body_without_structural_children(node: ET.Element) -> str:
    parts: list[str] = []
    if node.text and node.text.strip():
        parts.append(node.text)
    for child in node:
        if _lname(child.tag) in STRUCTURAL_XML_TYPES:
            if child.tail and child.tail.strip():
                parts.append(child.tail)
            continue
        text = "".join(child.itertext())
        if text.strip():
            parts.append(text)
        if child.tail and child.tail.strip():
            parts.append(child.tail)
    return _norm(" ".join(parts))


def extract_egov_law_metadata(data: bytes) -> dict:
    root = ET.fromstring(data)
    title = None
    law_num = None
    for elem in root.iter():
        name = _lname(elem.tag)
        if title is None and name == "LawTitle":
            value = _iter_text(elem)
            if value:
                title = value
        if law_num is None and name == "LawNum":
            value = _iter_text(elem)
            if value:
                law_num = value
        if title and law_num:
            break
    return {
        "title": title,
        "law_number": law_num,
        "law_type": root.attrib.get("LawType"),
        "lang": root.attrib.get("Lang"),
    }


def parse_egov_xml(data: bytes) -> list[ProvisionRecord]:
    root = ET.fromstring(data)
    records: list[ProvisionRecord] = []
    sequence = 0

    def walk(node: ET.Element, parent_key: str | None, ancestry: list[str]) -> None:
        nonlocal sequence
        tag = _lname(node.tag)
        this_parent = parent_key
        next_ancestry = ancestry

        if tag in STRUCTURAL_XML_TYPES:
            ptype = STRUCTURAL_XML_TYPES[tag]
            label = _first_child_text(node, LABEL_TAGS.get(tag, []))
            heading = _first_child_text(node, HEADING_TAGS.get(tag, []))
            num = node.attrib.get("Num") or node.attrib.get("Extract")
            stable = _norm(str(num or label or f"seq-{sequence + 1}")).replace("/", "-")
            key_part = f"{ptype}:{stable}"
            key = "/".join([*ancestry, key_part])
            sequence += 1
            records.append(
                ProvisionRecord(
                    provision_key=key,
                    parent_key=parent_key,
                    provision_type=ptype,
                    sequence_no=sequence,
                    display_label=label,
                    heading_text=heading,
                    body_text=_body_without_structural_children(node),
                    source_anchor=node.attrib.get("Id") or node.attrib.get("id"),
                    source_path=key,
                    source_meta={"xml_tag": tag, "attributes": dict(node.attrib)},
                )
            )
            this_parent = key
            next_ancestry = [*ancestry, key_part]

        # Traverse each XML node exactly once. Non-structural wrapper nodes
        # (LawBody/MainProvision/etc.) simply pass through the current parent context.
        for child in node:
            walk(child, this_parent, next_ancestry)

    walk(root, None, [])
    return records


class _BlockHTMLParser(HTMLParser):
    BLOCK_TAGS = {
        "p", "div", "li", "td", "th", "h1", "h2", "h3", "h4", "h5", "h6",
        "dt", "dd", "caption",
    }

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.blocks: list[tuple[str | None, str]] = []
        self._buf: list[str] = []
        self._anchor: str | None = None
        self._depth = 0

    def handle_starttag(self, tag: str, attrs):
        attrs_d = dict(attrs)
        if tag.lower() in self.BLOCK_TAGS:
            self._flush()
            self._depth += 1
            self._anchor = attrs_d.get("id") or attrs_d.get("name") or self._anchor
        if tag.lower() == "br":
            self._buf.append("\n")
        if tag.lower() == "a":
            self._anchor = attrs_d.get("id") or attrs_d.get("name") or self._anchor

    def handle_endtag(self, tag: str):
        if tag.lower() in self.BLOCK_TAGS:
            self._flush()
            self._depth = max(0, self._depth - 1)

    def handle_data(self, data: str):
        if data.strip():
            self._buf.append(data)

    def close(self):
        super().close()
        self._flush()

    def _flush(self):
        text = _norm(" ".join(self._buf))
        if text:
            self.blocks.append((self._anchor, text))
        self._buf = []
        self._anchor = None


def decode_html(data: bytes, content_type: str | None = None) -> str:
    candidates: list[str] = []
    if content_type:
        m = re.search(r"charset=([^;\s]+)", content_type, re.I)
        if m:
            candidates.append(m.group(1).strip("'\""))
    head = data[:4096].decode("ascii", errors="ignore")
    m = re.search(r"charset=[\"']?([^\"'\s/>;]+)", head, re.I)
    if m:
        candidates.append(m.group(1))
    candidates += ["utf-8", "cp932", "shift_jis", "euc_jp"]
    seen = set()
    for enc in candidates:
        key = enc.lower()
        if key in seen:
            continue
        seen.add(key)
        try:
            return data.decode(enc)
        except (UnicodeDecodeError, LookupError):
            pass
    return data.decode("utf-8", errors="replace")


def parse_regulation_html(data: bytes, content_type: str | None = None) -> list[ProvisionRecord]:
    parser = _BlockHTMLParser()
    parser.feed(decode_html(data, content_type))
    parser.close()

    records: list[ProvisionRecord] = []
    sequence = 0
    current_article_key: str | None = None
    current_paragraph_key: str | None = None
    current_appendix_key: str | None = None
    paragraph_counter = 0
    item_counter = 0

    for anchor, text in parser.blocks:
        if len(text) > 10000:
            continue

        if SUPPL_RE.match(text):
            sequence += 1
            key = f"supplementary:{sequence}"
            records.append(
                ProvisionRecord(
                    provision_key=key,
                    parent_key=None,
                    provision_type="supplementary",
                    sequence_no=sequence,
                    display_label="附則",
                    body_text=text,
                    source_anchor=anchor,
                    source_path=key,
                )
            )
            current_article_key = None
            current_paragraph_key = key
            current_appendix_key = None
            continue

        app = APPENDIX_RE.match(text)
        if app:
            sequence += 1
            label = _norm(app.group(0))
            ptype = "form" if label.startswith("様式") else "appendix"
            key = f"{ptype}:{label}:{sequence}"
            records.append(
                ProvisionRecord(
                    provision_key=key,
                    parent_key=None,
                    provision_type=ptype,
                    sequence_no=sequence,
                    display_label=label,
                    body_text=text,
                    source_anchor=anchor,
                    source_path=key,
                )
            )
            current_appendix_key = key
            current_article_key = None
            current_paragraph_key = key
            continue

        art = ARTICLE_RE.match(text)
        if art:
            sequence += 1
            article_label = _norm(art.group(0))
            key = f"article:{article_label}"
            suffix = 2
            existing = {x.provision_key for x in records}
            base = key
            while key in existing:
                key = f"{base}#{suffix}"
                suffix += 1
            remainder = _norm(text[art.end():])
            records.append(
                ProvisionRecord(
                    provision_key=key,
                    parent_key=None,
                    provision_type="article",
                    sequence_no=sequence,
                    display_label=article_label,
                    body_text=remainder,
                    source_anchor=anchor,
                    source_path=key,
                )
            )
            current_article_key = key
            current_paragraph_key = key
            current_appendix_key = None
            paragraph_counter = 0
            item_counter = 0
            continue

        if current_article_key:
            para = PARAGRAPH_RE.match(text)
            if para and para.group(2) and len(para.group(1)) <= 4:
                paragraph_counter += 1
                sequence += 1
                label = _norm(para.group(1))
                key = f"{current_article_key}/paragraph:{label}"
                records.append(
                    ProvisionRecord(
                        provision_key=key,
                        parent_key=current_article_key,
                        provision_type="paragraph",
                        sequence_no=sequence,
                        display_label=label,
                        body_text=_norm(para.group(2)),
                        source_anchor=anchor,
                        source_path=key,
                    )
                )
                current_paragraph_key = key
                item_counter = 0
                continue

            item = ITEM_RE.match(text)
            if item:
                item_counter += 1
                sequence += 1
                label = _norm(item.group(1))
                parent = current_paragraph_key or current_article_key
                key = f"{parent}/item:{label}:{item_counter}"
                records.append(
                    ProvisionRecord(
                        provision_key=key,
                        parent_key=parent,
                        provision_type="item",
                        sequence_no=sequence,
                        display_label=label,
                        body_text=_norm(item.group(2)),
                        source_anchor=anchor,
                        source_path=key,
                    )
                )
                continue

            # First paragraph often has no explicit paragraph number.
            if text and current_paragraph_key == current_article_key:
                paragraph_counter += 1
                sequence += 1
                key = f"{current_article_key}/paragraph:implicit-{paragraph_counter}"
                records.append(
                    ProvisionRecord(
                        provision_key=key,
                        parent_key=current_article_key,
                        provision_type="paragraph",
                        sequence_no=sequence,
                        display_label=None,
                        body_text=text,
                        source_anchor=anchor,
                        source_path=key,
                        source_meta={"implicit_number": True},
                    )
                )
                current_paragraph_key = key
                continue

        if current_appendix_key and text:
            sequence += 1
            key = f"{current_appendix_key}/block:{sequence}"
            records.append(
                ProvisionRecord(
                    provision_key=key,
                    parent_key=current_appendix_key,
                    provision_type="appendix_block",
                    sequence_no=sequence,
                    body_text=text,
                    source_anchor=anchor,
                    source_path=key,
                )
            )

    if not records:
        # Notices, designations, agreements, and similar official documents may
        # contain no numbered Article structure at all. Preserve the full visible
        # body as one citable Provision instead of reporting a false parse gap.
        meaningful: list[str] = []
        seen: set[str] = set()
        for _anchor, text in parser.blocks:
            value = _norm(text)
            if not value or value in seen:
                continue
            if value.startswith(("selectTab(", "iPadLoadStyle(", "e000000")):
                continue
            seen.add(value)
            meaningful.append(value)
        body = "\n".join(meaningful)
        if body:
            records.append(
                ProvisionRecord(
                    provision_key="document_body:1",
                    parent_key=None,
                    provision_type="document_body",
                    sequence_no=1,
                    display_label=None,
                    heading_text=None,
                    body_text=body,
                    source_anchor=None,
                    source_path="document_body:1",
                    source_meta={"fallback": True, "reason": "no_numbered_provisions"},
                )
            )

    return records


def parse_legal_document(data: bytes, mime_type: str | None, filename: str | None = None) -> list[ProvisionRecord]:
    name = (filename or "").lower()
    mime = (mime_type or "").lower()
    if name.endswith(".xml") or "xml" in mime:
        return parse_egov_xml(data)
    if name.endswith((".html", ".htm")) or "html" in mime:
        return parse_regulation_html(data, mime_type)
    return []
