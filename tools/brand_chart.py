"""Add branding overlay to an existing chart image.

brand_chart(base_path, title, bullets) -> out_path
- overlays title top-left, bullets bottom-left on a semi-transparent panel
- overlays repo logo.png at bottom-right if present
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


def brand_chart(base_path: str, title: str, bullets: list[str]) -> str:
    p = Path(base_path)
    if not p.exists():
        return base_path
    try:
        img = Image.open(p).convert("RGBA")
        draw = ImageDraw.Draw(img)
        w, h = img.size

        # fonts (fall back to default if unavailable)
        try:
            font_title = ImageFont.truetype("arial.ttf", 26)
            font_sub = ImageFont.truetype("arial.ttf", 16)
            font_b = ImageFont.truetype("arial.ttf", 14)
        except Exception:
            font_title = ImageFont.load_default()
            font_sub = ImageFont.load_default()
            font_b = ImageFont.load_default()

        pad = 12
        header_h = 64

        # top header band
        _header_box = [0, 0, w, header_h]
        overlay = Image.new("RGBA", (w, header_h), (8, 10, 20, 220))
        img.paste(overlay, (0, 0), overlay)

        # title on header (left)
        try:
            draw.text((pad, pad), title, font=font_title, fill=(255, 255, 255, 255))
        except Exception:
            draw.text((pad, pad), title, font=font_sub, fill=(255, 255, 255, 255))

        # small branding badge on top-right
        badge_text = "LeanTrader"
        bt_w, bt_h = draw.textsize(badge_text, font=font_b)
        bx1 = w - pad
        bx0 = bx1 - (bt_w + pad * 2)
        by0 = pad
        by1 = by0 + bt_h + pad
        draw.rectangle([bx0, by0, bx1, by1], fill=(255, 255, 255, 20))
        draw.text((bx0 + pad, by0 + 2), badge_text, font=font_b, fill=(230, 230, 230, 255))

        # info panel bottom-left for bullets/details
        bullets = bullets or []
        if bullets:
            lines = bullets[:6]
            txt = "\n".join(lines)
            # measure text box and constrain width
            _max_w = int(w * 0.44)
            # naive wrap: if too long, truncate lines
            lines2 = []
            for L in lines:
                if len(L) > 80:
                    lines2.append(L[:77] + "...")
                else:
                    lines2.append(L)
            txt = "\n".join(lines2)
            b_w, b_h = draw.multiline_textsize(txt, font=font_b)
            bx0 = pad
            by1 = h - pad
            by0 = by1 - (b_h + pad * 2)
            bx1 = bx0 + b_w + pad * 2
            # subtle translucent panel
            draw.rectangle([bx0, by0, bx1, by1], fill=(6, 8, 12, 200))
            draw.multiline_text((bx0 + pad, by0 + pad), txt, font=font_b, fill=(230, 230, 230, 255))

        # overlay logo if present
        try:
            logo = Path("logo.png")
            if logo.exists():
                lg = Image.open(logo).convert("RGBA")
                lw = int(w * 0.12)
                lh = int(lg.size[1] * (lw / lg.size[0]))
                lg = lg.resize((lw, lh), Image.LANCZOS)
                img.paste(lg, (w - lw - 12, h - lh - 12), lg)
        except Exception:
            pass

    except Exception:
        return base_path

    out = str(p.parent / (p.stem + "_branded" + p.suffix))
    img.save(out)
    return out
