from pathlib import Path
import os

from pathlib import Path
import os
from typing import Any, Dict, Optional

from dotenv import load_dotenv
from gql.transport.aiohttp import AIOHTTPTransport
from gql import gql, Client

PROJECT_ROOT = Path(__file__).resolve().parent
ENV_FILE = PROJECT_ROOT / "root.env"
load_dotenv(dotenv_path=ENV_FILE)


class GraphQLClient:
  def __init__(self):
    dev_api_endpoint = os.getenv("dev_api_endpoint")
    dev_api_key = os.getenv("dev_api_key")
    if not dev_api_endpoint or not dev_api_key:
      raise RuntimeError("Missing dev_api_endpoint or dev_api_key in root.env")

    self.endpoint = dev_api_endpoint
    self.api_key = dev_api_key
    timeout = 60

    transport = AIOHTTPTransport(
      url=self.endpoint,
      headers={"x-api-key": self.api_key},
      timeout=timeout,
    )

    self.client = Client(
      transport=transport,
      fetch_schema_from_transport=False,
      execute_timeout=timeout,
    )

    print(f"Using API endpoint: {self.endpoint}")
    print(f"Using API key: {self.api_key}")

  async def execute_query(self, query: str, variables: Optional[Dict[str, Any]], pagination_key: Optional[str] = None) -> Any:
    query_document = gql(query)
    async with self.client as session:
      return await session.execute(query_document)







