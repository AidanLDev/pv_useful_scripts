from os import getenv
from pathlib import Path
from typing import Any, Dict, Optional
from dotenv import load_dotenv
from gql.transport.aiohttp import AIOHTTPTransport
from gql import gql, Client

PROJECT_ROOT = Path(__file__).resolve().parent
ENV_FILE = PROJECT_ROOT / "root.env"
load_dotenv(dotenv_path=ENV_FILE)


class GraphQLClient:
    def __init__(self):
        dev_api_endpoint = getenv("dev_api_endpoint")
        dev_api_key = getenv("dev_api_key")
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

    async def get_query(
        self,
        query: str,
        id: str,
        variables: Optional[Dict[str, Any]] = None,
    ) -> Any:
        query_document = gql(query)
        query_variables: Dict[str, Any] = dict(variables or {})
        query_variables["id"] = id

        async with self.client as session:
            return await session.execute(
                query_document, variable_values=query_variables
            )

    async def list_query(
        self,
        query: str,
        pagination_key: str,
        variables: Optional[Dict[str, Any]] = None,
    ) -> Any:
        if not pagination_key:
            raise ValueError("pagination_key is required for list_query")

        query_document = gql(query)
        all_items = []
        merged_response: Optional[Dict[str, Any]] = None
        base_variables: Dict[str, Any] = dict(variables or {})

        async with self.client as session:
            next_token = base_variables.get("nextToken")

            while True:
                page_variables = dict(base_variables)
                if next_token:
                    page_variables["nextToken"] = next_token
                else:
                    page_variables.pop("nextToken", None)

                response = await session.execute(
                    query_document, variable_values=page_variables
                )
                if merged_response is None:
                    merged_response = response

                page_data = response.get(pagination_key)
                if not isinstance(page_data, dict):
                    raise ValueError(
                        f"Expected response['{pagination_key}'] to be a dict for pagination"
                    )

                page_items = page_data.get("items", [])
                if not isinstance(page_items, list):
                    raise ValueError(
                        f"Expected response['{pagination_key}']['items'] to be a list"
                    )

                all_items.extend(page_items)
                next_token = page_data.get("nextToken")

                if not next_token:
                    break

            if merged_response is None:
                return {}

            merged_response[pagination_key]["items"] = all_items
            merged_response[pagination_key]["nextToken"] = None
            return merged_response
