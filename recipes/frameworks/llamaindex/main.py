"""llamaindex — pack unbounded RAG retrieval into a token budget, reversibly.

A retriever cheerfully returns six oversized nodes; stuffing them all into the prompt blows the
context window. contextkit packs the retrieved nodes to a budget, compressing the big ones with
squeeze (`evict="compress"`) and dropping what still won't fit — and prints a receipt. Each
compressed chunk keeps a handle that restores the original byte-for-byte.

Offline: real LlamaIndex retriever + fake OpenAI-shaped client. Run:
  uv run python recipes/frameworks/llamaindex/main.py
"""

from types import SimpleNamespace

from cendor.contextkit import Block, Context
from cendor.core import bus, instrument
from llama_index.core.retrievers import BaseRetriever
from llama_index.core.schema import NodeWithScore, QueryBundle, TextNode

MODEL = "gpt-4o"


class DocsRetriever(BaseRetriever):
    """A real LlamaIndex retriever returning six oversized nodes (highest score first)."""

    def _retrieve(self, query_bundle: QueryBundle):
        nodes = []
        for i in range(6):
            body = (
                f"Policy section {i}: duplicate-charge refunds are issued within five "
                f"business days once verified by billing. "
            ) * 40
            node = TextNode(text=body, id_=f"doc-{i}")
            nodes.append(NodeWithScore(node=node, score=1.0 - i * 0.1))
        return nodes


def fake_openai():
    class Completions:
        def create(self, **kwargs):
            return SimpleNamespace(usage=SimpleNamespace(prompt_tokens=2800, completion_tokens=120))

    return SimpleNamespace(chat=SimpleNamespace(completions=Completions()))


def main() -> None:
    nodes = DocsRetriever().retrieve("How are duplicate charges refunded?")
    print(f"retriever returned {len(nodes)} nodes")

    ctx = Context(budget_tokens=3000, model=MODEL, reserve_output=200)
    ctx.add(
        Block(
            "Answer only from the retrieved policy sections.", priority=10, pin=True, role="system"
        )
    )
    ctx.add(Block("How are duplicate charges refunded?", priority=9, pin=True, role="user"))
    for rank, nws in enumerate(nodes):
        # higher-ranked nodes get higher priority; oversized ones are compressed, not chopped
        ctx.add(Block(nws.node.text, priority=8 - rank, evict="compress", role="user"))
    messages = ctx.assemble()

    report = ctx.report()
    print(report)

    # The compressed chunks keep a reversible handle — restore one byte-for-byte.
    compressed = [d for d in report.decisions if d.action == "compressed" and d.handle]
    if compressed:
        restored = compressed[0].handle.expand()
        node_texts = {n.node.text for n in nodes}
        print(
            f"\ncompressed a chunk; handle.expand() restores the original: {restored in node_texts}"
        )

    seen: list = []
    bus.subscribe(seen.append)
    client = instrument(fake_openai())
    client.chat.completions.create(model=MODEL, messages=messages)
    print(f"sent {len(messages)} packed messages -> {MODEL}, cost ${seen[0].cost.amount}")

    # Measured ending: the retrieved nodes really were packed to a budget, one chunk really did
    # compress reversibly, and the call that carried them really was priced.
    assert compressed, "nothing was compressed - the budget was never tight enough to bite"
    assert restored in node_texts, "handle.expand() did not restore the chunk byte-for-byte"
    assert seen[0].cost and seen[0].cost.amount > 0, "the packed call was not priced"


if __name__ == "__main__":
    main()
