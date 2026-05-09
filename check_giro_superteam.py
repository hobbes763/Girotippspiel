import requests
from bs4 import BeautifulSoup
import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

url = "https://www.giroditalia.it/en/classifiche/di-tappa/1/"
headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept-Language": "en,de;q=0.9",
}
resp = requests.get(url, headers=headers, timeout=15)
soup = BeautifulSoup(resp.text, "lxml")

# Find panel with data-category="tab-classifica-CLSQA"
panel = soup.find(attrs={"data-category": "tab-classifica-CLSQA"})
if panel:
    print("Found Super Team panel:")
    print(panel.prettify()[:5000])
else:
    print("Not found via data-category. Searching raw HTML...")
    idx = resp.text.find("tab-classifica-CLSQA")
    # Find all occurrences
    start = 0
    count = 0
    while True:
        idx = resp.text.find("tab-classifica-CLSQA", start)
        if idx < 0 or count > 5:
            break
        print(f"\n--- Occurrence {count+1} at {idx} ---")
        print(resp.text[idx-50:idx+300])
        start = idx + 1
        count += 1
