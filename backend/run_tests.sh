#!/bin/bash
# Test runner script for DataManager tests

echo "=================================="
echo "DataManager Test Suite Runner"
echo "=================================="
echo ""

# Colors for output
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Function to run specific test
run_specific_test() {
    echo -e "${BLUE}Running specific test: $1${NC}"
    pytest "$1" -v -s
}

# Function to run all tests
run_all_tests() {
    echo -e "${BLUE}Running all DataManager tests...${NC}"
    pytest app/managers/data_manager/tests/ -v -s
}

# Function to run with coverage
run_with_coverage() {
    echo -e "${BLUE}Running tests with coverage report...${NC}"
    pytest app/managers/data_manager/tests/ -v --cov=app/managers/data_manager --cov-report=html --cov-report=term
}

# Main menu
echo "Select test option:"
echo "1) Run all DataManager tests"
echo "2) Run get_current_time() tests only"
echo "3) Run tests with coverage report"
echo "4) Run specific test file"
echo ""

# Check if argument provided
if [ -n "$1" ]; then
    case $1 in
        "all")
            run_all_tests
            ;;
        "time")
            run_specific_test "app/managers/data_manager/tests/test_get_current_time.py"
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
    read -p "Enter option (1-4): " option
    
    case $option in
        1)
            run_all_tests
            ;;
        2)
            run_specific_test "app/managers/data_manager/tests/test_get_current_time.py"
            ;;
        3)
            run_with_coverage
            ;;
        4)
            read -p "Enter test file path: " filepath
            run_specific_test "$filepath"
            ;;
        *)
            echo -e "${YELLOW}Invalid option${NC}"
            exit 1
            ;;
    esac
fi

echo ""
echo -e "${GREEN}Test execution complete!${NC}"
