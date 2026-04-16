import asyncio
import importlib.util
import sys
from pathlib import Path

report_test_location_id = "19283b06-a93a-4e92-aee1-076e4ad7512c"
report_test_two_location_id = "4cb8a7e9-09ea-4025-bf03-572072ba88f9"

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
CUSTOMER_DATA_BY_LOCATION_ID_AND_DATE_TIME_QUERY = (
    queries_module.CUSTOMER_DATA_BY_LOCATION_ID_AND_DATE_TIME_QUERY
)

mutations_module_path = PROJECT_ROOT / "graphql" / "mutations.py"
mutations_spec = importlib.util.spec_from_file_location(
    "local_graphql_mutations", mutations_module_path
)
if mutations_spec is None or mutations_spec.loader is None:
    raise RuntimeError(f"Unable to load mutations module at {mutations_module_path}")

mutations_module = importlib.util.module_from_spec(mutations_spec)
mutations_spec.loader.exec_module(mutations_module)
CREATE_CUSTOMER_DATA_MUTATION = mutations_module.CREATE_CUSTOMER_DATA_MUTATION


def build_customer_data_input(row: dict) -> dict:
    mutation_input = {
        "locationID": report_test_two_location_id,
        "dateTime": row.get("dateTime"),
        "siteID": row.get("siteID"),
        "measureName": row.get("measureName"),
        "tag": row.get("tag"),
        "measureDataType": row.get("measureDataType"),
        "measureUnit": row.get("measureUnit"),
        "measureValueString": row.get("measureValueString"),
        "measureValueNumber": row.get("measureValueNumber"),
        "measureValueBoolean": row.get("measureValueBoolean"),
        "customerDataUserId": row.get("customerDataUserId"),
    }

    return {key: value for key, value in mutation_input.items() if value is not None}


async def main() -> None:
    client = GraphQLClient()

    response = await client.list_query(
        query=CUSTOMER_DATA_BY_LOCATION_ID_AND_DATE_TIME_QUERY,
        pagination_key="customerDataByLocationIDAndDateTime",
        variables={"locationID": report_test_location_id},
    )

    payload = response.get("customerDataByLocationIDAndDateTime", {})
    customer_data_to_copy = payload.get("items", [])

    print(
        f"Found {len(customer_data_to_copy)} customer data row(s) for location {report_test_location_id}"
    )

    total_rows = len(customer_data_to_copy)
    copied_count = 0
    failed_count = 0

    for index, row in enumerate(customer_data_to_copy, start=1):
        mutation_input = build_customer_data_input(row)

        try:
            await client.execute_mutation(
                mutation=CREATE_CUSTOMER_DATA_MUTATION,
                variables={"input": mutation_input},
            )
            copied_count += 1
        except Exception as exc:
            failed_count += 1
            print(f"Failed to copy row {index}: {exc}")

        if index % 100 == 0 or index == total_rows:
            print(f"Progress: {index}/{total_rows} processed")

    print(
        "Copy complete. "
        f"Successfully copied: {copied_count}. Failed: {failed_count}. "
        f"Target location: {report_test_two_location_id}"
    )


if __name__ == "__main__":
    asyncio.run(main())
