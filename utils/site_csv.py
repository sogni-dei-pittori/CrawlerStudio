import csv
from datetime import datetime
from urllib.parse import urlparse
from utils.paths import DATA_ROOT
CSV_ROOT = DATA_ROOT

class SiteCsvStore:
    def __init__(self, start_url: str, filename: str = "pages.csv"):
        time_str = datetime.now().strftime("%Y-%m-%d_%H-%M")
        domain = urlparse(start_url).netloc
        self.path = CSV_ROOT / domain / time_str / filename
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def save(self, row: dict) -> None:
        is_new = not self.path.exists() or self.path.stat().st_size == 0
        with open(self.path,'a',encoding='utf-8-sig', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=list(row.keys()))
            if is_new:
                writer.writeheader()
            writer.writerow(row)

