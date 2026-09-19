from utils.paths import DATA_ROOT

d = DATA_ROOT / "top.baidu.com"
print(d)                 # 期望：<项目根>\data\top.baidu.com
print(d.is_dir())        # 期望：True
print([p.name for p in d.iterdir()][:5])
# 期望：一串快照目录名，如 ['2026-09-15_18-35', '2026-09-15_19-39', ...]
print([p.name for p in d.iterdir() if (p / "board.csv").is_file()])
# 期望：只有真正有 board.csv 的那些，数量 15