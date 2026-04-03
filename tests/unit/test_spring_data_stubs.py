from __future__ import annotations

from synapps.indexer.java.spring_data_stubs import (
    CRUD_REPOSITORY_METHODS,
    JPA_REPOSITORY_METHODS,
    SPRING_DATA_PARENTS,
    inject_spring_data_stubs,
)


def test_crud_repository_methods_count() -> None:
    assert len(CRUD_REPOSITORY_METHODS) == 11


def test_crud_repository_methods_names() -> None:
    expected = {
        "save", "saveAll", "findById", "findAll", "findAllById",
        "count", "delete", "deleteById", "existsById",
        "deleteAll", "deleteAllById",
    }
    assert set(CRUD_REPOSITORY_METHODS) == expected


def test_jpa_repository_methods_count() -> None:
    assert len(JPA_REPOSITORY_METHODS) == 6


def test_jpa_repository_methods_names() -> None:
    expected = {
        "flush", "saveAndFlush", "saveAllAndFlush",
        "deleteInBatch", "deleteAllInBatch", "getReferenceById",
    }
    assert set(JPA_REPOSITORY_METHODS) == expected


def test_no_overlap_between_lists() -> None:
    crud_set = set(CRUD_REPOSITORY_METHODS)
    jpa_set = set(JPA_REPOSITORY_METHODS)
    assert crud_set.isdisjoint(jpa_set), f"Overlap found: {crud_set & jpa_set}"


def test_all_method_names_are_nonempty_strings() -> None:
    for name in CRUD_REPOSITORY_METHODS + JPA_REPOSITORY_METHODS:
        assert isinstance(name, str) and len(name) > 0


def test_no_duplicate_names_in_crud() -> None:
    assert len(CRUD_REPOSITORY_METHODS) == len(set(CRUD_REPOSITORY_METHODS))


def test_no_duplicate_names_in_jpa() -> None:
    assert len(JPA_REPOSITORY_METHODS) == len(set(JPA_REPOSITORY_METHODS))


def test_spring_data_parents_is_frozenset() -> None:
    assert isinstance(SPRING_DATA_PARENTS, frozenset)


def test_spring_data_parents_count() -> None:
    assert len(SPRING_DATA_PARENTS) == 5


def test_spring_data_parents_names() -> None:
    expected = {
        "CrudRepository", "JpaRepository", "PagingAndSortingRepository",
        "MongoRepository", "ReactiveCrudRepository",
    }
    assert SPRING_DATA_PARENTS == expected


def test_inject_spring_data_stubs_is_callable() -> None:
    assert callable(inject_spring_data_stubs)
