# To get started run pip install -r ./requirements.txt from the root

import asyncio
import importlib.util
import sys
from pathlib import Path

internal_account_id = "5fd00820-8d4e-4457-8975-41990c5e87ca"
report_test_location_id = "19283b06-a93a-4e92-aee1-076e4ad7512c"

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from api_client import GraphQLClient

queries_module_path = PROJECT_ROOT / "graphql" / "queries.py"
queries_spec = importlib.util.spec_from_file_location(
    "local_graphql_queries", queries_module_path
)
if queries_spec is None or queries_spec.loader is None:
    raise RuntimeError(f"Unable to load queries module at {queries_module_path}")

queries_module = importlib.util.module_from_spec(queries_spec)
queries_spec.loader.exec_module(queries_module)
SCORES_BY_LOCATION_ID_QUERY = queries_module.SCORES_BY_LOCATION_ID_QUERY


async def main() -> None:
    client = GraphQLClient()

    response = await client.list_query(
        query=SCORES_BY_LOCATION_ID_QUERY,
        pagination_key="scoresByLocationID",
        variables={"locationID": report_test_location_id},
    )

    payload = response.get("scoresByLocationID", {})
    items = payload.get("items", [])

    print(f"Found {len(items)} score row(s) for location {report_test_location_id}")
    for index, item in enumerate(items, start=1):
        print(f"{index}. score={item.get('score')} dateTime={item.get('dateTime')}")


if __name__ == "__main__":
    asyncio.run(main())
