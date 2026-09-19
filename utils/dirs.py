from datetime import datetime
from utils.paths import DATA_ROOT
CSV_ROOT = DATA_ROOT

def make_run_dir(domain: str):
    time_str = datetime.now().strftime("%Y-%m-%d_%H-%M") 
    out_dir = CSV_ROOT / domain / time_str
    out_dir.mkdir(parents=True, exist_ok=True)
    return out_dir

