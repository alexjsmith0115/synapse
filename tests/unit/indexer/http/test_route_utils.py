from __future__ import annotations

from synapse.indexer.http.route_utils import normalize_route


def test_strips_type_constraints() -> None:
    assert normalize_route("{id:guid}") == "/{id}"
    assert normalize_route("{id:int}") == "/{id}"
    assert normalize_route("items/{slug:alpha}") == "/items/{slug}"


def test_strips_regex_constraints() -> None:
    assert normalize_route("{slug:[a-z]+}") == "/{slug}"


def test_ensures_leading_slash() -> None:
    assert normalize_route("api/items") == "/api/items"


def test_strips_trailing_slash() -> None:
    assert normalize_route("/api/items/") == "/api/items"


def test_collapses_double_slashes() -> None:
    assert normalize_route("/api//items") == "/api/items"


def test_preserves_case() -> None:
    assert normalize_route("/Api/Items") == "/Api/Items"


def test_empty_returns_root() -> None:
    assert normalize_route("") == "/"


def test_already_normalized() -> None:
    assert normalize_route("/api/items/{id}") == "/api/items/{id}"


def test_combines_class_and_method_route() -> None:
    assert normalize_route("api/items", "{id:guid}") == "/api/items/{id}"


def test_method_route_only() -> None:
    assert normalize_route("", "items/{id}") == "/items/{id}"


def test_tilde_override_ignores_class_route() -> None:
    assert normalize_route("api/items", "~/api/auth/me") == "/api/auth/me"


def test_multiple_params() -> None:
    assert normalize_route("api/{org:guid}/items/{id:int}") == "/api/{org}/items/{id}"


# ---------------------------------------------------------------------------
# Client route normalization — base URL variable stripping
# ---------------------------------------------------------------------------

def test_strip_base_url_variable_basic() -> None:
    from synapse.indexer.http.route_utils import strip_base_url_variable
    assert strip_base_url_variable("{apiBaseUrl}/api/users/me") == "/api/users/me"


def test_strip_base_url_variable_preserves_normal_routes() -> None:
    from synapse.indexer.http.route_utils import strip_base_url_variable
    assert strip_base_url_variable("/api/users/me") == "/api/users/me"


def test_strip_base_url_variable_preserves_param_routes() -> None:
    from synapse.indexer.http.route_utils import strip_base_url_variable
    assert strip_base_url_variable("/api/users/{id}") == "/api/users/{id}"


def test_strip_base_url_variable_multiple_prefixes() -> None:
    from synapse.indexer.http.route_utils import strip_base_url_variable
    assert strip_base_url_variable("{baseUrl}/items") == "/items"


def test_strip_base_url_variable_only_variable() -> None:
    """A route that is only a variable should be returned as-is (no path after it)."""
    from synapse.indexer.http.route_utils import strip_base_url_variable
    assert strip_base_url_variable("{apiBaseUrl}") == "{apiBaseUrl}"


def test_strip_base_url_variable_empty() -> None:
    from synapse.indexer.http.route_utils import strip_base_url_variable
    assert strip_base_url_variable("") == ""


def test_strip_base_url_variable_with_backtick_style() -> None:
    """Variables with dots or special chars in the name should also be stripped."""
    from synapse.indexer.http.route_utils import strip_base_url_variable
    assert strip_base_url_variable("{config.apiUrl}/api/health") == "/api/health"


# ---------------------------------------------------------------------------
# JAX-RS constraint normalization -- PROD-03 regression tests
# ---------------------------------------------------------------------------

def test_strips_jaxrs_constraint_with_space() -> None:
    """JAX-RS uses space after colon: {id: [0-9]+} -- PROD-03 regression."""
    assert normalize_route("{id: [0-9]+}") == "/{id}"


def test_strips_jaxrs_constraint_combined() -> None:
    assert normalize_route("items/{slug: [a-z]+}") == "/items/{slug}"


def test_strips_jaxrs_constraint_special_chars() -> None:
    assert normalize_route("{name: [A-Za-z\\s]+}") == "/{name}"
