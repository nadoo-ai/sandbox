#!/usr/bin/env python3
"""
Nadoo Plugin Execution Wrapper

This script runs inside the plugin-runner Docker container and provides:
1. RestrictedPython sandbox
2. Resource monitoring
3. Error handling
4. Secure output formatting
"""

import json
import sys
import traceback
import signal
import resource
from pathlib import Path
from typing import Any, Dict

from RestrictedPython import compile_restricted, safe_builtins, limited_builtins
from RestrictedPython.Guards import safe_globals, guarded_iter_unpack_sequence


def setup_resource_limits():
    """Set OS-level resource limits"""
    # Memory limit (256MB)
    memory_limit = 256 * 1024 * 1024
    resource.setrlimit(resource.RLIMIT_AS, (memory_limit, memory_limit))

    # CPU time limit (30 seconds)
    resource.setrlimit(resource.RLIMIT_CPU, (30, 30))

    # File size limit (10MB)
    file_limit = 10 * 1024 * 1024
    resource.setrlimit(resource.RLIMIT_FSIZE, (file_limit, file_limit))

    # Number of open files
    resource.setrlimit(resource.RLIMIT_NOFILE, (64, 64))

    # Number of processes
    resource.setrlimit(resource.RLIMIT_NPROC, (10, 10))


def timeout_handler(signum, frame):
    """Handle execution timeout"""
    raise TimeoutError("Plugin execution exceeded time limit")


def create_safe_builtins():
    """
    Create safe builtins for RestrictedPython

    Only allow safe operations, block dangerous functions
    """
    # Start with limited builtins
    safe_dict = limited_builtins.copy()

    # Add safe built-in functions
    safe_dict.update({
        'abs': abs,
        'all': all,
        'any': any,
        'bool': bool,
        'dict': dict,
        'enumerate': enumerate,
        'filter': filter,
        'float': float,
        'int': int,
        'isinstance': isinstance,
        'len': len,
        'list': list,
        'map': map,
        'max': max,
        'min': min,
        'range': range,
        'reversed': reversed,
        'round': round,
        'set': set,
        'sorted': sorted,
        'str': str,
        'sum': sum,
        'tuple': tuple,
        'zip': zip,

        # Safe iteration
        '_iter_unpack_sequence_': guarded_iter_unpack_sequence,
        '_getiter_': lambda obj: iter(obj),

        # Allow basic assertions
        'True': True,
        'False': False,
        'None': None,
    })

    # Explicitly block dangerous functions
    blocked = {
        '__import__': None,  # No dynamic imports
        'eval': None,        # No eval
        'exec': None,        # No exec
        'compile': None,     # No compile
        'open': None,        # No file access
        'input': None,       # No user input
        'help': None,
        'exit': None,
        'quit': None,
    }

    safe_dict.update(blocked)

    return safe_dict


def execute_plugin(code: str, config: Dict[str, Any]) -> Dict[str, Any]:
    """
    Execute plugin code in RestrictedPython sandbox

    Args:
        code: Plugin source code
        config: Execution configuration (context, parameters, etc.)

    Returns:
        Execution result dictionary
    """
    # Compile code with RestrictedPython
    byte_code = compile_restricted(
        code,
        filename='<plugin>',
        mode='exec'
    )

    # Check for compilation errors
    if byte_code.errors:
        return {
            'success': False,
            'error': 'Compilation failed',
            'details': byte_code.errors
        }

    # Create safe execution environment
    safe_dict = create_safe_builtins()

    # Add plugin SDK components
    try:
        from nadoo_plugin import PluginContext
        from nadoo_plugin.api import InternalAPIClient

        # Create context from config
        context = PluginContext(
            execution_id=config['execution_id'],
            plugin_id=config['plugin_id'],
            workspace_id=config['workspace_id'],
            user_id=config.get('user_id'),
            application_id=config.get('application_id'),
            model_uuid=config.get('model_uuid'),
            workflow_id=config.get('workflow_id'),
            node_id=config.get('node_id'),
            permissions=config.get('permissions', []),
            allowed_tool_ids=config.get('allowed_tool_ids', []),
            allowed_kb_ids=config.get('allowed_kb_ids', []),
            sdk_version=config.get('sdk_version', '0.1.0'),
            plugin_version=config.get('plugin_version', '1.0.0'),
            debug_mode=config.get('debug_mode', False),
        )

        # Create API client
        api_client = InternalAPIClient(
            base_url=config['api_base_url'],
            token=config['api_token'],
            context=context
        )

        # Add to safe globals
        safe_dict.update({
            'context': context,
            'api': api_client,
            'parameters': config.get('parameters', {}),
        })

    except Exception as e:
        return {
            'success': False,
            'error': 'Failed to initialize plugin environment',
            'details': str(e)
        }

    # Execute plugin code
    try:
        exec(byte_code.code, safe_dict)

        # Find plugin class
        plugin_class = None
        for name, obj in safe_dict.items():
            if (isinstance(obj, type) and
                hasattr(obj, '__bases__') and
                any(base.__name__ == 'NadooPlugin' for base in obj.__bases__)):
                plugin_class = obj
                break

        if not plugin_class:
            return {
                'success': False,
                'error': 'No NadooPlugin subclass found in code'
            }

        # Instantiate and execute
        plugin_instance = plugin_class()
        plugin_instance.initialize(context=context, api=api_client)

        result = plugin_instance.execute(
            config['tool_name'],
            config.get('parameters', {})
        )

        plugin_instance.finalize()

        return {
            'success': True,
            'result': result,
            'logs': context.get_logs(),
            'trace': context.get_trace(),
        }

    except Exception as e:
        return {
            'success': False,
            'error': str(e),
            'traceback': traceback.format_exc(),
        }


def main():
    """Main execution entry point"""
    try:
        # Setup resource limits
        setup_resource_limits()

        # Setup timeout (30 seconds)
        signal.signal(signal.SIGALRM, timeout_handler)
        signal.alarm(30)

        # Read configuration from stdin or environment
        config_path = Path('/plugin/config.json')
        if config_path.exists():
            with open(config_path, 'r') as f:
                config = json.load(f)
        else:
            # Read from stdin
            config = json.loads(sys.stdin.read())

        # Read plugin code
        code_path = Path('/plugin/code') / config.get('entry_point', 'main.py')
        if not code_path.exists():
            print(json.dumps({
                'success': False,
                'error': f'Plugin code not found: {code_path}'
            }))
            sys.exit(1)

        with open(code_path, 'r', encoding='utf-8') as f:
            code = f.read()

        # Execute plugin
        result = execute_plugin(code, config)

        # Output result as JSON
        print(json.dumps(result, ensure_ascii=False, indent=2))

        # Exit with appropriate code
        sys.exit(0 if result['success'] else 1)

    except TimeoutError as e:
        print(json.dumps({
            'success': False,
            'error': 'Execution timeout',
            'details': str(e)
        }))
        sys.exit(124)  # Standard timeout exit code

    except MemoryError as e:
        print(json.dumps({
            'success': False,
            'error': 'Memory limit exceeded',
            'details': str(e)
        }))
        sys.exit(137)  # Standard OOM exit code

    except Exception as e:
        print(json.dumps({
            'success': False,
            'error': 'Unexpected error',
            'details': str(e),
            'traceback': traceback.format_exc()
        }))
        sys.exit(1)

    finally:
        # Cancel alarm
        signal.alarm(0)


if __name__ == '__main__':
    main()
