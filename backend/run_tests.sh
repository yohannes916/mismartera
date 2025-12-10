#!/bin/bash
# Test runner script for Backend Test Suite

echo "======================================="
echo "Backend Test Suite Runner"
echo "======================================="
echo ""

# Colors for output
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# Function to run all tests
run_all_tests() {
    echo -e "${BLUE}Running all tests...${NC}"
    pytest tests/ -v
}

# Function to run unit tests only
run_unit_tests() {
    echo -e "${BLUE}Running unit tests (fast, mocks only)...${NC}"
    pytest tests/unit/ -v -m unit
}

# Function to run integration tests
run_integration_tests() {
    echo -e "${BLUE}Running integration tests (with test database)...${NC}"
    pytest tests/integration/ -v -m integration
}

# Function to run e2e tests
run_e2e_tests() {
    echo -e "${BLUE}Running E2E tests (full workflows, slow)...${NC}"
    pytest tests/e2e/ -v -m e2e
}

# Function to run scanner tests only
run_scanner_tests() {
    echo -e "${BLUE}Running scanner framework tests...${NC}"
    pytest tests/ -k scanner -v
}

# Function to run with coverage
run_with_coverage() {
    echo -e "${BLUE}Running tests with coverage report...${NC}"
    pytest tests/ -v \
        --cov=app/threads/scanner_manager \
        --cov=scanners \
        --cov=app/threads/quality \
        --cov-report=html \
        --cov-report=term-missing
    echo ""
    echo -e "${GREEN}Coverage report generated in htmlcov/index.html${NC}"
}

# Function to run fast tests only
run_fast_tests() {
    echo -e "${BLUE}Running fast tests (skip slow tests)...${NC}"
    pytest tests/ -v -m "not slow"
}

# Function to run specific test
run_specific_test() {
    echo -e "${BLUE}Running specific test: $1${NC}"
    pytest "$1" -v -s
}

# Main menu
echo "Select test option:"
echo "1)  Run all tests"
echo "2)  Run unit tests only (fast)"
echo "3)  Run integration tests"
echo "4)  Run E2E tests (slow)"
echo "5)  Run scanner tests only"
echo "6)  Run fast tests (skip slow)"
echo "7)  Run with coverage report"
echo "8)  Run specific test file"
echo ""

# Check if argument provided
if [ -n "$1" ]; then
    case $1 in
        "all")
            run_all_tests
            ;;
        "unit")
            run_unit_tests
            ;;
        "integration")
            run_integration_tests
            ;;
        "e2e")
            run_e2e_tests
            ;;
        "scanner" | "scanners")
            run_scanner_tests
            ;;
        "fast")
            run_fast_tests
            ;;
        "coverage")
            run_with_coverage
            ;;
        *)
            echo -e "${YELLOW}Running: $1${NC}"
            run_specific_test "$1"
            ;;
    esac
else
    # Interactive mode
    read -p "Enter option (1-8): " option
    
    case $option in
        1)
            run_all_tests
            ;;
        2)
            run_unit_tests
            ;;
        3)
            run_integration_tests
            ;;
        4)
            run_e2e_tests
            ;;
        5)
            run_scanner_tests
            ;;
        6)
            run_fast_tests
            ;;
        7)
            run_with_coverage
            ;;
        8)
            read -p "Enter test file path: " filepath
            run_specific_test "$filepath"
            ;;
        *)
            echo -e "${RED}Invalid option${NC}"
            exit 1
            ;;
    esac
fi

echo ""
echo -e "${GREEN}Test execution complete!${NC}"
