from tools.mle_dojo_mcp.mock_server import MLEDojoMockServer
from tools.mle_dojo_mcp.server import MLEDojoRealServer

def get_mle_dojo_client(use_mock: bool = True):
    if use_mock:
        return MLEDojoMockServer()
    return MLEDojoRealServer()

__all__ = ["MLEDojoMockServer", "MLEDojoRealServer", "get_mle_dojo_client"]
