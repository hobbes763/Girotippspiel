import requests
from bs4 import BeautifulSoup
import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept-Language": "de,en;q=0.9",
}

url = "https://www.procyclingstats.com/race/giro-d-italia/2026/stage-2"
resp = requests.get(url, headers=HEADERS, timeout=15)
soup = BeautifulSoup(resp.text, "lxml")

rider_links = soup.find_all("a", href=lambda h: h and "/rider/" in h)
print(f"Fahrer-Links auf der Seite: {len(rider_links)}")
for a in rider_links[:10]:
    print(f"  {a.get_text(strip=True):30s}  {a['href']}")

# Zeige alle Überschriften
print("\nAlle Überschriften:")
for tag in soup.find_all(["h2","h3","h4"]):
    print(f"  {tag.name}: {tag.get_text(strip=True)[:80]}")
