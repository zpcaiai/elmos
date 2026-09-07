from __future__ import annotations
import math
def finite_population_sample_size(population,confidence_z=1.96,margin=0.05,p=0.5):
 if population<=0 or margin<=0: raise ValueError("invalid")
 n0=(confidence_z**2*p*(1-p))/(margin**2)
 return math.ceil(n0/(1+(n0-1)/population))
def proportional_allocation(strata,total):
 s=sum(strata.values())
 if s<=0 or total<=0: raise ValueError("invalid")
 raw={k:total*v/s for k,v in strata.items()}
 return {k:max(1,round(v)) for k,v in raw.items()}
