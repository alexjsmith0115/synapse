from __future__ import annotations

import logging

from synapps.graph.connection import GraphConnection

log = logging.getLogger(__name__)

CRUD_REPOSITORY_METHODS: tuple[str, ...] = (
    "save", "saveAll", "findById", "findAll", "findAllById",
    "count", "delete", "deleteById", "existsById",
    "deleteAll", "deleteAllById",
)

JPA_REPOSITORY_METHODS: tuple[str, ...] = (
    "flush", "saveAndFlush", "saveAllAndFlush",
    "deleteInBatch", "deleteAllInBatch", "getReferenceById",
)

SPRING_DATA_PARENTS: frozenset[str] = frozenset({
    "CrudRepository", "JpaRepository", "PagingAndSortingRepository",
    "MongoRepository", "ReactiveCrudRepository",
})

_ALL_STUB_METHODS: tuple[str, ...] = CRUD_REPOSITORY_METHODS + JPA_REPOSITORY_METHODS


def inject_spring_data_stubs(conn: GraphConnection, language: str = "java") -> int:
    """
    Create stub Method nodes for inherited Spring Data repository methods on concrete
    repository interfaces. Runs after INHERITS edges exist in the graph.

    Returns the number of stub Method nodes created/updated.
    """
    from synapps.graph.nodes import upsert_method
    from synapps.graph.edges import upsert_contains_symbol

    parent_list = list(SPRING_DATA_PARENTS)
    rows = conn.query(
        "MATCH (repo:Interface)-[:INHERITS]->(parent) "
        "WHERE parent.name IN $parents "
        "RETURN repo.full_name, repo.name",
        {"parents": parent_list},
    )

    if not rows:
        log.debug("No Spring Data repository interfaces found in graph")
        return 0

    count = 0
    for repo_full_name, repo_name in rows:
        if not repo_full_name:
            continue
        for method_name in _ALL_STUB_METHODS:
            stub_full_name = f"{repo_full_name}.{method_name}"
            upsert_method(
                conn,
                full_name=stub_full_name,
                name=method_name,
                signature=method_name,
                is_abstract=False,
                is_static=False,
                file_path="",
                line=None,
                end_line=0,
                language=language,
                stub=True,
            )
            upsert_contains_symbol(conn, repo_full_name, stub_full_name)
            count += 1

    log.info("Spring Data stub injection: %d stub methods created/updated for %d repositories", count, len(rows))
    return count
