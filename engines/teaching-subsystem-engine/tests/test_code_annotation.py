from __future__ import annotations

from elmos_teaching_subsystem.code_annotation import (
    AnnotationStore, Annotation, SourceAnchor, AnnotationType
)

def test_annotation_crud():
    store = AnnotationStore()
    anchor = SourceAnchor("f.py", 0, 10, 1, 2)
    ann = Annotation("a1", anchor, "Content", AnnotationType.EXPLANATION, "alice", "2023", ["tag1"])
    
    # Create
    store.create(ann)
    assert store.read("a1") is not None
    
    # Update
    ann.content = "New"
    store.update(ann)
    assert store.read("a1").content == "New" # type: ignore
    
    # Delete
    store.delete("a1")
    assert store.read("a1") is None

def test_annotation_query():
    store = AnnotationStore()
    anchor = SourceAnchor("f.py", 0, 10, 1, 2)
    ann1 = Annotation("a1", anchor, "C1", AnnotationType.EXPLANATION, "alice", "2023", ["t1"])
    ann2 = Annotation("a2", anchor, "C2", AnnotationType.WARNING, "bob", "2023", ["t2"])
    store.create(ann1)
    store.create(ann2)
    
    res = store.query(type=AnnotationType.EXPLANATION)
    assert len(res) == 1
    assert res[0].annotation_id == "a1"

    res = store.query(tag="t2")
    assert len(res) == 1
    assert res[0].annotation_id == "a2"
