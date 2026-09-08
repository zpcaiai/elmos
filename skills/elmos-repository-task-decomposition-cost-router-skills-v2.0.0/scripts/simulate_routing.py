from pathlib import Path
import yaml, json
ROOT=Path(__file__).resolve().parents[1]
policy=yaml.safe_load((ROOT/'config/router-policy.yaml').read_text())

def candidates(task_class, minimum_tier='L0'):
    order=['L0','L1','L2','L3','L4']
    min_i=order.index(minimum_tier)
    preferred=policy['task_class_preferences'].get(task_class, [])
    eligible=[]
    for m in preferred:
        tier=max((i for i,t in enumerate(order) if m in policy['tiers'].get(t,[])), default=0)
        if tier>=min_i or minimum_tier=='L0': eligible.append(m)
    if eligible: return eligible
    merged=[]
    for t in order[min_i:]:
        for m in policy['tiers'][t]:
            if m not in merged: merged.append(m)
    return merged

examples=[('docs_config_boilerplate','L0'),('backend_standard','L1'),('complex_debug','L2'),('architecture_contracts','L3'),('long_horizon_migration','L4')]
for tc,tier in examples:
    print(f'{tc:30} {tier}: {candidates(tc,tier)}')
