#!/usr/bin/env python3
"""OPTIONAL native LangGraph + SQLite interrupt fixture; no model/network calls.
Run start and resume as TWO processes with the same --db after approved dependency setup.
Does not test host authentication, application snapshots or production side effects.
"""
import argparse,json,sys
from importlib.metadata import version
from typing import TypedDict

def main():
    try:
        from langgraph.graph import StateGraph,START,END
        from langgraph.types import interrupt,Command
        from langgraph.checkpoint.sqlite import SqliteSaver
    except ImportError as e:print(json.dumps(dict(status='not_run',reason='optional native dependency missing',detail=str(e))));return 3
    p=argparse.ArgumentParser();p.add_argument('--phase',choices=['start','resume'],required=True);p.add_argument('--db',required=True);a=p.parse_args()
    class State(TypedDict,total=False):
        evidence_ref:str
        answer:int
        learning_result:str
    def ask(state):return {'answer':interrupt({'question':'subtotal>=10000，subtotal=10000时是否进入分支？答1或0。','evidence_ref':state['evidence_ref']})}
    def assess(state):return {'learning_result':'correct' if state['answer']==1 else 'review_evidence'}
    b=StateGraph(State);b.add_node('ask',ask);b.add_node('assess',assess);b.add_edge(START,'ask');b.add_edge('ask','assess');b.add_edge('assess',END)
    with SqliteSaver.from_conn_string(a.db) as saver:
        g=b.compile(checkpointer=saver);cfg={'configurable':{'thread_id':'local-fixture-only'},'recursion_limit':8}
        result=g.invoke({'evidence_ref':'fixture:discount'} if a.phase=='start' else Command(resume=1),config=cfg)
        print(json.dumps(dict(phase=a.phase,native_version=version('langgraph'),result=result,production_qualified=False),default=str,ensure_ascii=False))
    return 0
if __name__=='__main__':sys.exit(main())
