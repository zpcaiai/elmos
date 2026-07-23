
from pathlib import Path
import argparse, shutil
p=argparse.ArgumentParser(); p.add_argument('target'); args=p.parse_args()
src=Path(__file__).resolve().parents[2]/'templates'/'product-convergence'; dst=Path(args.target)
dst.mkdir(parents=True,exist_ok=True)
for f in src.glob('*.json'): shutil.copy2(f,dst/f.name)
(dst/'evidence').mkdir(exist_ok=True); (dst/'results').mkdir(exist_ok=True)
print(dst)
