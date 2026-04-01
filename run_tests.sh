#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"
source .venv/bin/activate

RED='\033[0;31m'
GREEN='\033[0;32m'
BOLD='\033[1m'
RESET='\033[0m'

run_unit=true
run_integration=true

for arg in "$@"; do
    case "$arg" in
        --unit) run_unit=true; run_integration=false ;;
        --integration) run_unit=false; run_integration=true ;;
        --help|-h)
            echo "Usage: $0 [--unit | --integration]"
            echo "  (no flags)       Run both unit and integration tests"
            echo "  --unit           Run unit tests only"
            echo "  --integration    Run integration tests only"
            exit 0
            ;;
    esac
done

failed=0

if $run_unit; then
    echo -e "${BOLD}=== Unit Tests ===${RESET}"
    if pytest tests/unit/ -v; then
        echo -e "${GREEN}Unit tests passed${RESET}"
    else
        echo -e "${RED}Unit tests failed${RESET}"
        failed=1
    fi
fi

if $run_integration; then
    echo -e "\n${BOLD}=== Integration Tests ===${RESET}"
    echo "Ensuring Memgraph is running..."
    docker compose up -d

    integration_tests=(
        tests/integration/test_mcp_tools.py
        tests/integration/test_mcp_tools_typescript.py
        tests/integration/test_mcp_tools_python.py
        tests/integration/test_mcp_tools_java.py
        tests/integration/test_cli_commands.py
        tests/integration/test_cli_commands_python.py
        tests/integration/test_cli_commands_typescript.py
        tests/integration/test_cli_commands_java.py
        tests/integration/test_http_endpoints.py
        tests/integration/test_http_cross_language.py
        tests/integration/test_cross_namespace_implements.py
    )

    for test_file in "${integration_tests[@]}"; do
        echo -e "\n${BOLD}--- ${test_file} ---${RESET}"
        if pytest "$test_file" -v -m integration; then
            echo -e "${GREEN}PASSED: ${test_file}${RESET}"
        else
            echo -e "${RED}FAILED: ${test_file}${RESET}"
            failed=1
        fi
    done
fi

echo ""
if [ $failed -eq 0 ]; then
    echo -e "${GREEN}${BOLD}All tests passed!${RESET}"
else
    echo -e "${RED}${BOLD}Some tests failed.${RESET}"
    exit 1
fi
