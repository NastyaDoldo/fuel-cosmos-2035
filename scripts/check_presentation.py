import re
import sys
from html.parser import HTMLParser

sys.stdout.reconfigure(encoding="utf-8")

VOID = {"meta", "br", "img", "hr", "input", "link", "area", "base", "col", "embed", "source", "track", "wbr"}


class P(HTMLParser):
    def __init__(self):
        super().__init__()
        self.stack = []
        self.errs = []

    def handle_starttag(self, t, attrs):
        if t not in VOID:
            self.stack.append(t)

    def handle_endtag(self, t):
        if t in VOID:
            return
        if self.stack and self.stack[-1] == t:
            self.stack.pop()
        else:
            self.errs.append(f"mismatch {t} at line {self.getpos()[0]}")


html = open(r"docs\presentation.html", encoding="utf-8").read()
p = P()
p.feed(html)
print("unclosed:", p.stack)
print("errors:", p.errs[:5])
print("slides:", len(re.findall(r'class="slide"', html)))
