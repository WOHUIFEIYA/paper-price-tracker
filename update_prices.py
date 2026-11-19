#!/usr/bin/env python3
"""Fetch the latest listed paper prices from 100ppi and update data.json."""
from datetime import datetime, timezone, timedelta
from html.parser import HTMLParser
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
    req=urllib.request.Request(URL, headers={"User-Agent":"Mozilla/5.0 (compatible; PaperPriceTracker/1.0)"})
    with urllib.request.urlopen(req, timeout=30) as response: html=response.read().decode("utf-8", "replace")
    parser=TableParser(); parser.feed(html)
    records=[]
    for cells in parser.rows:
        row=" ".join(cells)
        supplier=next((name for name in TARGETS if name in row), None)
        if not supplier: continue
        dates=re.findall(r"20\d{2}-\d{2}-\d{2}", row)
        prices=re.findall(r"(?<!\d)(\d{3,5})\s*元\s*/\s*吨", row)
        if not prices: prices=re.findall(r"(?<!\d)(\d{3,5})(?=\s|$)", row)
        if not dates or not prices: continue
        records.append({"supplier":supplier,"kind":"黄板纸","grade":"A级","type":"终端价","price":int(prices[0]),"date":dates[-1]})
    if not records: raise RuntimeError("未能从来源页面解析到目标报价；可能是页面结构变化或访问受限。")
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
