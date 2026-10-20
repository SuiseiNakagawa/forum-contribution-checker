"""Builds '../Install Forum button.html' from forum_helper.js.
Run after editing forum_helper.js:  python3 bookmarklet/build.py"""
from pathlib import Path
from urllib.parse import quote

here = Path(__file__).parent
code = (here / "forum_helper.js").read_text()
href = "javascript:" + quote(code, safe="")
page = (here / "install_template.html").read_text().replace("{{HREF}}", href)
out = here.parent / "Install Forum button.html"
out.write_text(page)
print(f"wrote {out} ({len(href):,} characters in the button)")
