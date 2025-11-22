#!/bin/bash
#
# Build Nadoo Sandbox Docker Images
#

set -e

# Colors
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}   Nadoo Sandbox - Build Script${NC}"
echo -e "${BLUE}========================================${NC}"
echo ""

# Navigate to sandbox directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SANDBOX_ROOT="$(dirname "$SCRIPT_DIR")"
cd "$SANDBOX_ROOT"

# Build sandbox service
echo -e "${YELLOW}Building sandbox service...${NC}"
docker build -t nadoo-sandbox:latest -f Dockerfile .
echo -e "${GREEN}✓ Sandbox service built${NC}"
echo ""

# Build plugin runner
echo -e "${YELLOW}Building plugin runner...${NC}"

# First, build the SDK wheel if not exists
SDK_ROOT="$SANDBOX_ROOT/../nadoo-plugin-sdk"
if [ -d "$SDK_ROOT" ]; then
    cd "$SDK_ROOT"
    if [ ! -d "dist" ] || [ -z "$(ls -A dist/*.whl 2>/dev/null)" ]; then
        echo -e "${YELLOW}Building nadoo-plugin-sdk...${NC}"

        # Check if poetry is available
        if command -v poetry &> /dev/null; then
            poetry build
        else
            # Fallback to pip
            echo -e "${YELLOW}Poetry not found, using pip to build...${NC}"
            python -m pip install --upgrade build
            python -m build
        fi
    fi

    # Copy wheel to sandbox directory
    cp dist/*.whl "$SANDBOX_ROOT/"
    cd "$SANDBOX_ROOT"
fi

docker build -t nadoo-plugin-runner:latest -f Dockerfile.plugin-runner .

# Clean up wheel file
rm -f nadoo_plugin_sdk*.whl

echo -e "${GREEN}✓ Plugin runner built${NC}"
echo ""

echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}   Build completed!${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""

echo -e "${BLUE}Images built:${NC}"
docker images | grep "nadoo-"
echo ""

echo -e "${YELLOW}Next steps:${NC}"
echo -e "  1. Start services:"
echo -e "     ${BLUE}docker-compose up -d${NC}"
echo -e ""
echo -e "  2. Check logs:"
echo -e "     ${BLUE}docker-compose logs -f sandbox${NC}"
echo -e ""
echo -e "  3. Test health:"
echo -e "     ${BLUE}curl http://localhost:8002/health${NC}"
echo ""
