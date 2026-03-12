from unittest.mock import MagicMock, patch
from datetime import datetime, timezone

from synapse.graph.lookups import check_staleness


def _conn(return_value: list) -> MagicMock:
    conn = MagicMock()
    conn.query.return_value = return_value
    return conn


def test_check_staleness_stale_file() -> None:
    indexed_at = "2026-03-11T10:00:00+00:00"
    conn = _conn([[indexed_at, "/proj/Foo.cs"]])
    with patch("synapse.graph.lookups.os.path.getmtime", return_value=datetime(2026, 3, 11, 11, 0, tzinfo=timezone.utc).timestamp()):
        with patch("synapse.graph.lookups.os.path.exists", return_value=True):
            result = check_staleness(conn, "/proj/Foo.cs")
    assert result is not None
    assert result["is_stale"] is True


def test_check_staleness_fresh_file() -> None:
    indexed_at = "2026-03-11T12:00:00+00:00"
    conn = _conn([[indexed_at, "/proj/Foo.cs"]])
    with patch("synapse.graph.lookups.os.path.getmtime", return_value=datetime(2026, 3, 11, 10, 0, tzinfo=timezone.utc).timestamp()):
        with patch("synapse.graph.lookups.os.path.exists", return_value=True):
            result = check_staleness(conn, "/proj/Foo.cs")
    assert result is not None
    assert result["is_stale"] is False


def test_check_staleness_file_not_in_graph() -> None:
    conn = _conn([])
    result = check_staleness(conn, "/proj/Unknown.cs")
    assert result is None


def test_check_staleness_file_deleted_from_disk() -> None:
    conn = _conn([["2026-03-11T10:00:00+00:00", "/proj/Gone.cs"]])
    with patch("synapse.graph.lookups.os.path.exists", return_value=False):
        result = check_staleness(conn, "/proj/Gone.cs")
    assert result is None
