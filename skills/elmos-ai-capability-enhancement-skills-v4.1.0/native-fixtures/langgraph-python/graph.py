from typing import TypedDict
class State(TypedDict):
    input: str
    answer: str
def answer(state: State) -> State:
    return {**state, "answer": state["input"]}
