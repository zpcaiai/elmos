import importlib.util, sys
from pathlib import Path
import pytest
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
from validate_package import validate, check_dag, load_yaml
from install_skills import safe_destination, install

def test_package_structure():
    result=validate(ROOT)
    assert result['status']=='PASS',result['errors']
    assert result['counts']['skills']==34
    assert result['counts']['api_operations']==14
    assert result['counts']['json_schemas']==15

def test_dependency_cycle_is_rejected():
    with pytest.raises(ValueError,match='DEPENDENCY_CYCLE'):check_dag({'a':['b'],'b':['a']})

def test_unknown_dependency_is_rejected():
    with pytest.raises(ValueError,match='UNKNOWN_DEPENDENCY'):check_dag({'a':['missing']})

def test_duplicate_yaml_key_is_rejected(tmp_path):
    p=tmp_path/'a.yaml';p.write_text('a: 1\na: 2\n')
    with pytest.raises(ValueError,match='DUPLICATE_YAML_KEY'):load_yaml(p)

def test_install_refuses_symlink_path(tmp_path):
    (tmp_path/'actual').mkdir();(tmp_path/'.agents').symlink_to(tmp_path/'actual',target_is_directory=True)
    with pytest.raises(ValueError,match='SYMLINK'):safe_destination(tmp_path,Path('.agents/skills/demo'))

def test_install_refuses_no_git(tmp_path):
    with pytest.raises(ValueError,match='GIT_REPOSITORY'):install(tmp_path,'codex')

def test_destination_traversal_is_rejected(tmp_path):
    with pytest.raises(ValueError,match='UNSAFE_DESTINATION'):safe_destination(tmp_path,Path('../outside'))
