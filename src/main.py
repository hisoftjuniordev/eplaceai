from mcp.server.fastmcp import FastMCP

from src.database import lifespan
from src.tools import read_tools, write_tools, workflow_tools

mcp = FastMCP(
    "si-payroll-mcp",
    lifespan=lifespan,
    instructions=(
        "Mini ERP za slovenske plače. Upravljaš zaposlene, evidenco ur, potne naloge, "
        "dopuste in mesečne obračune plač po slovenski zakonodaji (2026). "
        "Za kritične operacije (potrjevanje plač, brisanje) zahtevaj potrditev."
    ),
)

read_tools.register(mcp)
write_tools.register(mcp)
workflow_tools.register(mcp)

if __name__ == "__main__":
    mcp.run()
