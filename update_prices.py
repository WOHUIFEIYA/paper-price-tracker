#!/usr/bin/env python3
"""Fetch the latest listed paper prices from 100ppi and update data.json."""
from datetime import datetime, timezone, timedelta
from html.parser import HTMLParser
import html as html_lib
from pathlib import Path
import json
import re
import urllib.request

URL = "https://fz.100ppi.com/price/"
TARGETS = {"浙江绍兴华宇", "浙江嘉兴景兴", "浙江嘉兴山鹰"}
OUT = Path(__file__).with_name("data.json")

class TableParser(HTMLParser):
    def __init__(self):
        super().__init__(); self.rows=[]; self.row=None; self.cell=None
    def handle_starttag(self, tag, attrs):
        if tag == "tr": self.row=[]
        elif tag in ("td", "th") and self.row is not None: self.cell=[]
    def handle_data(self, data):
        if self.cell is not None: self.cell.append(data)
    def handle_endtag(self, tag):
        if tag in ("td", "th") and self.cell is not None:
            self.row.append(" ".join(" ".join(self.cell).split())); self.cell=None
        elif tag == "tr" and self.row is not None:
            self.rows.append(self.row); self.row=None

def fetch():
    def get_page(cookie=None):
        headers={
            "User-Agent": (
                "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
            ),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            "Cache-Control": "no-cache",
            "Referer": "https://fz.100ppi.com/",
        }
        if cookie:
            headers["Cookie"] = cookie
        req=urllib.request.Request(URL, headers=headers)
        with urllib.request.urlopen(req, timeout=30) as response:
            raw=response.read()
            content_type=response.headers.get("Content-Type", "")
            status=response.status
            encoding=response.headers.get_content_charset()
        if not encoding:
            meta=re.search(rb"<meta[^>]+charset\s*=\s*[\"']?([\w-]+)",raw[:8192],re.I)
            encoding=meta.group(1).decode("ascii","ignore") if meta else "utf-8"
        return raw, content_type, status, encoding, raw.decode(encoding,"replace")

    raw, content_type, status, encoding, html = get_page()

    # 100ppi may return a short JavaScript interstitial instead of its table.
    # Its script sets a temporary cookie and reloads the page; mirror that
    # cookie once so the scheduled, non-browser request can continue.
    if "正在进行安全检查" in html or "HW_CHECK" in html:
        cookie_match=re.search(
            r'document\.cookie\s*=\s*["\']([^"\']+)["\']\s*\+\s*["\']\s*=\s*["\']\s*\+\s*([\w$]+)',
            html,
        )
        if cookie_match:
            cookie_name, value_variable = cookie_match.groups()
            value_match=re.search(
                r'\b(?:var\s+)?' + re.escape(value_variable) + r'\s*=\s*["\']([^"\']+)["\']',
                html,
            )
            if value_match:
                raw, content_type, status, encoding, html = get_page(
                    f"{cookie_name}={value_match.group(1)}"
                )

    parser=TableParser(); parser.feed(html)
    source_rows=parser.rows
    # Also parse raw table rows in case a minor markup change confuses HTMLParser.
    for row_html in re.findall(r"<tr\b[^>]*>(.*?)</tr\s*>",html,re.I|re.S):
        cells=re.findall(r"<t[dh]\b[^>]*>(.*?)</t[dh]\s*>",row_html,re.I|re.S)
        source_rows.append([
            " ".join(html_lib.unescape(re.sub(r"<[^>]+>"," ",cell)).split())
            for cell in cells
        ])
    records=[]
    for cells in source_rows:
        row=" ".join(cells)
        supplier=next((name for name in TARGETS if name in row), None)
        if not supplier: continue
        dates=re.findall(r"20\d{2}-\d{2}-\d{2}", row)
        prices=re.findall(r"(?<!\d)([\d,]{3,7})\s*元\s*/\s*吨", row)
        if not dates or not prices: continue
        records.append({"supplier":supplier,"kind":"黄板纸","grade":"A级","type":"终端价","price":int(prices[0].replace(",","")),"date":dates[-1]})
    if not records:
        preview=" ".join(re.sub(r"<[^>]+>"," ",html[:2500]).split())[:700]
        found={name:(name in html) for name in sorted(TARGETS)}
        raise RuntimeError(
            f"未能解析到目标报价。HTTP {status}; "
            f"Content-Type={content_type!r}; encoding={encoding!r}; "
            f"HTML bytes={len(raw)}; target text found={found}; preview={preview!r}"
        )
    records=list({(r["supplier"],r["date"]):r for r in records}.values())
    previous={}
    if OUT.exists():
        try:
            previous=json.loads(OUT.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError): pass
    merged={(r["supplier"],r["date"]):r for r in previous.get("records",[])}
    merged.update({(r["supplier"],r["date"]):r for r in records})
    shanghai=timezone(timedelta(hours=8))
    result={"source":URL,"fetched_at":datetime.now(shanghai).strftime("%Y-%m-%d %H:%M:%S"),"records":sorted(merged.values(),key=lambda r:(r["date"],r["supplier"]),reverse=True)}
    OUT.write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(f"Saved {len(records)} source rows; {len(result['records'])} records retained.")

if __name__ == "__main__": fetch()
