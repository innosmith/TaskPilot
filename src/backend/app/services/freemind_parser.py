"""
FreeMind .mm XML → TaskPilot flow_data Konverter.

Parst die rekursive XML-Knotenstruktur und erzeugt eine flache
React-Flow-Darstellung (nodes + edges + viewport).

Nur Knotenstruktur (Text + Hierarchie + Links) — keine Bilder, Icons oder Styling.

MindMeister exportiert .mm als ZIP-Archiv (XML drin); normales FreeMind ist rohes XML.
Beide Varianten werden transparent behandelt.
"""

from __future__ import annotations

import io
import xml.etree.ElementTree as ET
import zipfile

NODE_X_SPACING = 300
NODE_Y_SPACING = 80


def _unpack_mm(raw: bytes) -> str:
    """ZIP-verpacktes oder rohes XML entpacken."""
    if raw[:2] == b"PK":
        with zipfile.ZipFile(io.BytesIO(raw)) as zf:
            for name in zf.namelist():
                if name.endswith(".mm") or name.endswith(".xml"):
                    return zf.read(name).decode("utf-8")
            return zf.read(zf.namelist()[0]).decode("utf-8")

    for enc in ("utf-8", "latin-1"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


def parse_freemind_xml(xml_content: str | bytes) -> dict:
    """
    FreeMind .mm Inhalt in TaskPilot flow_data konvertieren.

    Akzeptiert rohes XML (str/bytes) oder ZIP-verpacktes .mm (bytes).
    Returns dict mit keys: nodes, edges, viewport.
    Raises ValueError bei ungültigem XML.
    """
    if isinstance(xml_content, bytes):
        xml_str = _unpack_mm(xml_content)
    else:
        xml_str = xml_content

    root_elem = ET.fromstring(xml_str)

    root_node = root_elem.find("node")
    if root_node is None:
        raise ValueError("Keine Root-Node im FreeMind-XML gefunden")

    nodes: list[dict] = []
    edges: list[dict] = []
    counter = [0]

    def _make_id() -> str:
        counter[0] += 1
        return f"n{counter[0]}"

    def _walk(
        elem: ET.Element,
        node_id: str,
        depth: int,
        parent_id: str | None,
        y_offset: list[float],
        side: str,
    ) -> None:
        label = elem.get("TEXT", "").strip()

        if not label:
            rc = elem.find("richcontent")
            if rc is not None:
                parts = [t.strip() for t in rc.itertext() if t.strip()]
                label = " ".join(parts) or "…"

        x = depth * NODE_X_SPACING
        if side == "left":
            x = -x

        y = y_offset[0]

        node_data: dict = {"label": label}
        link = elem.get("LINK")
        if link:
            node_data["url"] = link

        nodes.append({
            "id": node_id,
            "type": "mindmapNode",
            "position": {"x": x, "y": y},
            "data": node_data,
        })

        if parent_id:
            edges.append({
                "id": f"e-{parent_id}-{node_id}",
                "source": parent_id,
                "target": node_id,
                "type": "mindmapEdge",
            })

        children = elem.findall("node")
        if not children:
            y_offset[0] += NODE_Y_SPACING
            return

        for child in children:
            child_id = _make_id()
            child_side = child.get("POSITION", side) or side
            _walk(child, child_id, depth + 1, node_id, y_offset, child_side)

    root_children = root_node.findall("node")
    left_children = [c for c in root_children if c.get("POSITION") == "left"]
    right_children = [c for c in root_children if c.get("POSITION") != "left"]

    root_title = root_node.get("TEXT", "Importierte Mind-Map")
    nodes.append({
        "id": "root",
        "type": "mindmapNode",
        "position": {"x": 0, "y": 0},
        "data": {"label": root_title},
    })

    y_right = [-(len(right_children) * NODE_Y_SPACING) / 2]
    for child in right_children:
        _walk(child, _make_id(), 1, "root", y_right, "right")

    y_left = [-(len(left_children) * NODE_Y_SPACING) / 2]
    for child in left_children:
        _walk(child, _make_id(), 1, "root", y_left, "left")

    return {
        "nodes": nodes,
        "edges": edges,
        "viewport": {"x": 0, "y": 0, "zoom": 1},
    }


def extract_title(xml_content: str | bytes) -> str:
    """Titel (TEXT-Attribut der Root-Node) aus FreeMind-XML extrahieren."""
    if isinstance(xml_content, bytes):
        xml_str = _unpack_mm(xml_content)
    else:
        xml_str = xml_content

    root_elem = ET.fromstring(xml_str)
    root_node = root_elem.find("node")
    if root_node is None:
        return "Importierte Mind-Map"
    return root_node.get("TEXT", "Importierte Mind-Map")
