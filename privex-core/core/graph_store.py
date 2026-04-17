import os

try:
    from langchain_neo4j import Neo4jGraph
except Exception:
    Neo4jGraph = None


_graph_store = None


def get_graph_store():
    """Return a singleton Neo4jGraph instance or None when unavailable."""
    global _graph_store

    if _graph_store is not None:
        return _graph_store

    if Neo4jGraph is None:
        print("[graph-store] langchain_neo4j is not installed. GraphRAG disabled.")
        return None

    uri = os.getenv("NEO4J_URI", "").strip()
    username = os.getenv("NEO4J_USERNAME", "").strip()
    password = os.getenv("NEO4J_PASSWORD", "").strip()

    if not uri or not username or not password:
        print("[graph-store] Missing NEO4J_URI/NEO4J_USERNAME/NEO4J_PASSWORD. GraphRAG disabled.")
        return None

    try:
        _graph_store = Neo4jGraph(
            url=uri,
            username=username,
            password=password,
            refresh_schema=False,
        )
        return _graph_store
    except Exception as exc:
        print(f"[graph-store] Failed to connect to Neo4j: {exc}")
        _graph_store = None
        return None


def run_wcc_deduplication() -> None:
    """
    Entity Resolution: Collapses duplicate/similar nodes to prevent graph fragmentation.
    Requires the APOC plugin to physically merge nodes and preserve edges.
    """
    global _graph_store

    if _graph_store is None:
        _graph_store = get_graph_store()

    if _graph_store is None:
        return

    print("🕸️ [GraphRAG] Running Entity Deduplication...")

    # Heuristic string matching (simulating WCC clustering for App names)
    cypher_dedupe_apps = """
    MATCH (a:Application)
    WITH toLower(trim(a.name)) AS normalized_name, collect(a) AS duplicate_nodes
    WHERE size(duplicate_nodes) > 1
    CALL apoc.refactor.mergeNodes(duplicate_nodes, {properties: 'overwrite', mergeRels: true}) YIELD node
    RETURN count(node) AS merged_count
    """

    try:
        results = _graph_store.query(cypher_dedupe_apps)
        if results and results[0].get("merged_count", 0) > 0:
            print(f"🕸️ [GraphRAG] Successfully collapsed {results[0]['merged_count']} duplicate entities.")
    except Exception as exc:
        print(f"[GraphRAG] Deduplication failed (Is APOC installed in Neo4j?): {exc}")
