import copy,json
from pathlib import Path
import pytest
from elmos_assurance.assertions import evaluate_assertions,pointer,MISSING
R=Path(__file__).resolve().parents[1]
def fixtures():
 return (json.loads((R/'examples/assertion-program.example.json').read_text()),json.loads((R/'examples/typed-observation.example.json').read_text()))
def test_real_finite_assertion_interpreter():
 p,o=fixtures();assert evaluate_assertions(p,o)['status']=='PASS'
@pytest.mark.parametrize('value',[200,True,'201',None])
def test_wrong_type_or_value_is_not_equal(value):
 p,o=fixtures();o['data']['status']=value;assert evaluate_assertions(p,o)['status']=='FAIL'
@pytest.mark.parametrize('value',['NaN','Infinity','1e1',10.0,True])
def test_invalid_decimal_is_unknown(value):
 p,o=fixtures();o['data']['total']=value;assert evaluate_assertions(p,o)['status']=='UNKNOWN'
def test_missing_value_does_not_default_pass():
 p,o=fixtures();del o['data']['status'];assert evaluate_assertions(p,o)['status']=='UNKNOWN'
def test_empty_program_rejected():
 p,o=fixtures();p['assertions']=[];assert evaluate_assertions(p,o)['status']=='UNKNOWN'
def test_unfinished_observation_is_unknown():
 p,o=fixtures();o['completion']='TIMED_OUT';assert evaluate_assertions(p,o)['status']=='UNKNOWN'
def test_no_raw_script_operator():
 p,o=fixtures();p['assertions'][0]['op']='eval';assert evaluate_assertions(p,o)['status']=='UNKNOWN'
def test_explicit_absence_assertion():
 p,o=fixtures();p['assertions']=[{'id':'secret-not-returned','path':'/data/password','op':'not_exists'}]
 assert evaluate_assertions(p,o)['status']=='PASS'
 o['data']['password']=None;assert evaluate_assertions(p,o)['status']=='FAIL'
def test_json_pointer_escapes_and_absence():
 assert pointer({'a/b':{'~x':None}},'/a~1b/~0x')is None
 assert pointer({'xs':[0]},'/xs/01')is MISSING
 assert pointer({'xs':[0]},'/xs/1')is MISSING
 with pytest.raises(ValueError):pointer({},'/bad~escape')
def test_duplicate_assertion_id_rejected():
 p,o=fixtures();p['assertions'].append(p['assertions'][0]);assert evaluate_assertions(p,o)['status']=='UNKNOWN'
