from pathlib import Path
import shutil,sys
root=Path(__file__).resolve().parents[2]; src=root/'templates/batch46-complete'; dst=Path(sys.argv[1] if len(sys.argv)>1 else 'convergence-packs/reference-product')
dst.mkdir(parents=True,exist_ok=True)
for p in src.glob('*.json'): shutil.copy2(p,dst/p.name)
for d in ['evidence','reference-repositories','design-partner-evidence','reports','adr','migrations','release-train']:(dst/d).mkdir(exist_ok=True)
print(dst)
