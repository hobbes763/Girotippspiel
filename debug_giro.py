import requests
from bs4 import BeautifulSoup
import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept-Language": "en,de;q=0.9",
}

# Try various URLs for cumulative GC
urls = [
    "https://www.giroditalia.it/en/classifiche/classifica-generale/",
    "https://www.giroditalia.it/en/classifiche/generali/",
    "https://www.giroditalia.it/en/classifiche/",
]
for url in urls:
    r = requests.get(url, headers=HEADERS, timeout=10)
    print(f"{r.status_code}  {url}")
    if r.status_code == 200:
        soup = BeautifulSoup(r.text, "lxml")
        cats = [d["data-category"] for d in soup.find_all(attrs={"data-category": True})]
        print(f"  Tabs: {cats[:10]}")
        break
