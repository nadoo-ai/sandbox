#!/bin/bash
#
# Test Plugin Execution in Sandbox
#

set -e

GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}   Plugin Execution Test${NC}"
echo -e "${BLUE}========================================${NC}"
echo ""

# Check if sandbox is running
echo -e "${YELLOW}Checking sandbox service...${NC}"
if ! curl -s http://localhost:8002/health > /dev/null 2>&1; then
    echo -e "${RED}✗ Sandbox service not running${NC}"
    echo -e "${YELLOW}Start it with: docker-compose up -d${NC}"
    exit 1
fi
echo -e "${GREEN}✓ Sandbox service is running${NC}"
echo ""

# Check if plugin-runner image exists
echo -e "${YELLOW}Checking plugin-runner image...${NC}"
if ! docker images | grep -q "nadoo-plugin-runner"; then
    echo -e "${RED}✗ Plugin-runner image not found${NC}"
    echo -e "${YELLOW}Build it with: ./scripts/build.sh${NC}"
    exit 1
fi
echo -e "${GREEN}✓ Plugin-runner image exists${NC}"
echo ""

# Test 1: Simple Hello World Plugin
echo -e "${YELLOW}Test 1: Simple Hello World Plugin${NC}"

cat > /tmp/test_plugin.json <<'EOF'
{
  "plugin_code": "from nadoo_plugin import NadooPlugin, tool, parameter\n\nclass HelloPlugin(NadooPlugin):\n    \"\"\"Hello world plugin\"\"\"\n    \n    @tool(name=\"greet\", description=\"Greet someone\")\n    @parameter(\"name\", type=\"string\", required=True, description=\"Name to greet\")\n    def greet(self, name: str) -> dict:\n        self.context.log(f\"Greeting {name}\", level=\"info\")\n        return {\n            \"success\": True,\n            \"message\": f\"Hello, {name}!\",\n            \"timestamp\": str(self.context.started_at)\n        }",
  "entry_point": "main.py",
  "tool_name": "greet",
  "parameters": {"name": "World"},
  "execution_id": "test-001",
  "plugin_id": "hello-plugin",
  "workspace_id": "test-workspace",
  "permissions": [],
  "allowed_tool_ids": [],
  "allowed_kb_ids": [],
  "api_base_url": "http://localhost:8000",
  "api_token": "test-token",
  "timeout": 10,
  "memory_limit": "128m"
}
EOF

RESPONSE=$(curl -s -X POST http://localhost:8002/api/v1/plugin/execute \
  -H "Content-Type: application/json" \
  -H "X-API-Key: sandbox-api-key-change-in-production" \
  -d @/tmp/test_plugin.json)

if echo "$RESPONSE" | jq -e '.success == true' > /dev/null 2>&1; then
    echo -e "${GREEN}✓ Test 1 passed${NC}"
    echo "$RESPONSE" | jq '.'
else
    echo -e "${RED}✗ Test 1 failed${NC}"
    echo "$RESPONSE" | jq '.'
fi
echo ""

# Test 2: Plugin with Error Handling
echo -e "${YELLOW}Test 2: Plugin with Error Handling${NC}"

cat > /tmp/test_error.json <<'EOF'
{
  "plugin_code": "from nadoo_plugin import NadooPlugin, tool\n\nclass ErrorPlugin(NadooPlugin):\n    @tool(name=\"will_fail\", description=\"Test error handling\")\n    def will_fail(self) -> dict:\n        raise ValueError(\"Intentional error for testing\")",
  "entry_point": "main.py",
  "tool_name": "will_fail",
  "parameters": {},
  "execution_id": "test-002",
  "plugin_id": "error-plugin",
  "workspace_id": "test-workspace",
  "permissions": [],
  "allowed_tool_ids": [],
  "allowed_kb_ids": [],
  "api_base_url": "http://localhost:8000",
  "api_token": "test-token",
  "timeout": 10,
  "memory_limit": "128m"
}
EOF

RESPONSE=$(curl -s -X POST http://localhost:8002/api/v1/plugin/execute \
  -H "Content-Type: application/json" \
  -H "X-API-Key: sandbox-api-key-change-in-production" \
  -d @/tmp/test_error.json)

if echo "$RESPONSE" | jq -e '.success == false' > /dev/null 2>&1; then
    echo -e "${GREEN}✓ Test 2 passed (error correctly handled)${NC}"
    echo "$RESPONSE" | jq '{success, error}'
else
    echo -e "${RED}✗ Test 2 failed (error not caught)${NC}"
    echo "$RESPONSE" | jq '.'
fi
echo ""

# Test 3: RestrictedPython Blocks Dangerous Code
echo -e "${YELLOW}Test 3: RestrictedPython Security (should block eval)${NC}"

cat > /tmp/test_security.json <<'EOF'
{
  "plugin_code": "from nadoo_plugin import NadooPlugin, tool\n\nclass DangerousPlugin(NadooPlugin):\n    @tool(name=\"dangerous\", description=\"Try dangerous operation\")\n    def dangerous(self) -> dict:\n        # This should be blocked by RestrictedPython\n        result = eval('1 + 1')\n        return {\"result\": result}",
  "entry_point": "main.py",
  "tool_name": "dangerous",
  "parameters": {},
  "execution_id": "test-003",
  "plugin_id": "dangerous-plugin",
  "workspace_id": "test-workspace",
  "permissions": [],
  "allowed_tool_ids": [],
  "allowed_kb_ids": [],
  "api_base_url": "http://localhost:8000",
  "api_token": "test-token",
  "timeout": 10,
  "memory_limit": "128m"
}
EOF

RESPONSE=$(curl -s -X POST http://localhost:8002/api/v1/plugin/execute \
  -H "Content-Type: application/json" \
  -H "X-API-Key: sandbox-api-key-change-in-production" \
  -d @/tmp/test_security.json)

# Should fail because eval is blocked
if echo "$RESPONSE" | jq -e '.success == false' > /dev/null 2>&1; then
    echo -e "${GREEN}✓ Test 3 passed (dangerous code blocked)${NC}"
    echo "$RESPONSE" | jq '{success, error}' | head -10
else
    echo -e "${RED}✗ Test 3 failed (dangerous code not blocked!)${NC}"
    echo "$RESPONSE" | jq '.'
fi
echo ""

# Cleanup
rm -f /tmp/test_*.json

# Summary
echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}   All Tests Completed${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""
echo -e "${BLUE}Container cleanup:${NC}"
docker ps -a | grep nadoo-plugin-runner | awk '{print $1}' | xargs -r docker rm -f 2>/dev/null || true
echo -e "${GREEN}✓ Cleaned up test containers${NC}"
echo ""
