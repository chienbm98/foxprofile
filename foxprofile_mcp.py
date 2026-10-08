"""Start the FoxProfile MCP server from any working directory.

Point your MCP client at this file:  python /path/to/foxprofile/foxprofile_mcp.py
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.mcp_server.server import main  # noqa: E402

if __name__ == "__main__":
    main()
