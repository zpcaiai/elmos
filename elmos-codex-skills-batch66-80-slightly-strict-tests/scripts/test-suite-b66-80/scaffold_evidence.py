    #!/usr/bin/env python3
    import json, sys
    from pathlib import Path
    suite=Path(sys.argv[1]); case_id=sys.argv[2]
    cat=json.load(open(suite/'cases/catalog.json',encoding='utf-8'))['cases']; c=next((x for x in cat if x['case_id']==case_id),None)
    if not c: raise SystemExit('unknown case')
    out=suite/'evidence'/case_id; out.mkdir(parents=True,exist_ok=True)
    (out/'README.md').write_text(f"# Evidence {case_id}

Do not hand-edit passed status. Preserve raw logs and hashes.
",encoding='utf-8')
    for n in ('raw-command.log','replay.sh'): (out/n).touch()
    print(out)
