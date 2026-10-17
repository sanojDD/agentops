from functools import lru_cache

from langgraph.graph import END, START, StateGraph

from app.graph.edges import (
    route_after_generate,
    route_after_retrieve,
    route_after_validate,
    route_after_verify,
)
from app.graph.nodes import (
    fallback_node,
    generate_node,
    retrieve_node,
    rewrite_node,
    validate_node,
    verify_node,
)
from app.graph.state import AgentState


@lru_cache
def get_graph():
    g = StateGraph(AgentState)
    g.add_node("validate", validate_node)
    g.add_node("retrieve", retrieve_node)
    g.add_node("rewrite", rewrite_node)
    g.add_node("generate", generate_node)
    g.add_node("verify", verify_node)
    g.add_node("fallback", fallback_node)

    g.add_edge(START, "validate")
    g.add_conditional_edges("validate", route_after_validate, {"retrieve": "retrieve", END: END})
    g.add_conditional_edges(
        "retrieve",
        route_after_retrieve,
        {"generate": "generate", "rewrite": "rewrite", "fallback": "fallback"},
    )
    g.add_edge("rewrite", "retrieve")
    g.add_conditional_edges(
        "generate",
        route_after_generate,
        {"verify": "verify", "generate": "generate", END: END},
    )
    g.add_conditional_edges(
        "verify",
        route_after_verify,
        {"rewrite": "rewrite", "fallback": "fallback", END: END},
    )
    g.add_edge("fallback", END)
    return g.compile()
