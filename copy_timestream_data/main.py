from os import getenv
from pathlib import Path
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Iterable, List, Optional, Tuple

from boto3.session import Session
from botocore.exceptions import BotoCoreError, ClientError
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[1]
ENV_FILE = PROJECT_ROOT / "root.env"
load_dotenv(dotenv_path=ENV_FILE)

SOURCE_LOCATION_ID = "19283b06-a93a-4e92-aee1-076e4ad7512c"
TARGET_LOCATION_ID = "4cb8a7e9-09ea-4025-bf03-572072ba88f9"

AWS_PROFILE = getenv("TIMESTREAM_AWS_PROFILE") or getenv("AWS_PROFILE")
AWS_REGION = getenv("TIMESTREAM_REGION", "eu-west-1")
DATABASE_NAME = getenv("TIMESTREAM_DATABASE", "linevuDB")
TABLE_NAME = getenv("TIMESTREAM_TABLE", "dev-linevu-data")

BATCH_SIZE = 100


def quote_sql_literal(value: str) -> str:
    return value.replace("'", "''")


def build_source_query(source_location_id: str) -> str:
    return (
        f"SELECT to_nanoseconds(time) AS time_ns, * "
        f'FROM "{DATABASE_NAME}"."{TABLE_NAME}" '
        f"WHERE location_id = '{source_location_id}'"
    )


def build_location_count_query(location_id: str) -> str:
    return (
        f'SELECT COUNT(*) AS row_count FROM "{DATABASE_NAME}"."{TABLE_NAME}" '
        f"WHERE location_id = '{location_id}'"
    )


def build_time_range_query(location_id: str) -> str:
    return (
        "SELECT min(to_nanoseconds(time)) AS min_time_ns, "
        "max(to_nanoseconds(time)) AS max_time_ns "
        f'FROM "{DATABASE_NAME}"."{TABLE_NAME}" '
        f"WHERE location_id = '{location_id}'"
    )


def build_sample_record_query(record: Dict[str, Any]) -> str:
    location_id = next(
        (
            dimension["Value"]
            for dimension in record.get("Dimensions", [])
            if dimension.get("Name") == "location_id"
        ),
        "",
    )
    return (
        "SELECT measure_name, time, location_id "
        f'FROM "{DATABASE_NAME}"."{TABLE_NAME}" '
        f"WHERE location_id = '{quote_sql_literal(location_id)}' "
        f"AND measure_name = '{quote_sql_literal(record['MeasureName'])}' "
        f"AND to_nanoseconds(time) = {record['Time']} "
        "LIMIT 1"
    )


def parse_scalar_value(value: str, scalar_type: Optional[str]) -> Any:
    if scalar_type == "BIGINT":
        return int(value)
    if scalar_type == "DOUBLE":
        return float(value)
    if scalar_type == "BOOLEAN":
        return value.lower() == "true"
    return value


def parse_datum(datum: Dict[str, Any], type_info: Dict[str, Any]) -> Any:
    if datum.get("NullValue"):
        return None

    if "ScalarValue" in datum:
        scalar_type = type_info.get("ScalarType")
        return parse_scalar_value(datum["ScalarValue"], scalar_type)

    if "ArrayValue" in datum:
        array_type = (type_info.get("ArrayColumnInfo") or {}).get("Type", {})
        return [parse_datum(item, array_type) for item in datum["ArrayValue"]]

    if "RowValue" in datum:
        row_values = datum["RowValue"].get("Data", [])
        row_columns = type_info.get("RowColumnInfo", [])
        row_object: Dict[str, Any] = {}
        for index, row_column in enumerate(row_columns):
            if index >= len(row_values):
                break
            row_object[row_column["Name"]] = parse_datum(
                row_values[index], row_column.get("Type", {})
            )
        return row_object

    if "TimeSeriesValue" in datum:
        series_type = (type_info.get("TimeSeriesMeasureValueColumnInfo") or {}).get(
            "Type", {}
        )
        return [
            {
                "time": item.get("Time"),
                "value": parse_datum(item.get("Value", {}), series_type),
            }
            for item in datum["TimeSeriesValue"]
        ]

    return None


def normalize_rows(
    column_info: List[Dict[str, Any]], rows: List[Dict[str, Any]]
) -> List[Dict[str, Any]]:
    column_names = [column["Name"] for column in column_info]
    column_types = [column.get("Type", {}) for column in column_info]

    normalized: List[Dict[str, Any]] = []
    for row in rows:
        data = row.get("Data", [])
        row_object: Dict[str, Any] = {}
        for index, column_name in enumerate(column_names):
            if index >= len(data):
                row_object[column_name] = None
                continue
            row_object[column_name] = parse_datum(data[index], column_types[index])
        normalized.append(row_object)

    return normalized


def to_measure_value(value: Any, measure_type: str) -> str:
    if measure_type == "BOOLEAN":
        return "true" if bool(value) else "false"
    return str(value)


def infer_measure_from_row(row: Dict[str, Any]) -> Tuple[Optional[str], Optional[str]]:
    typed_measure_columns = [
        ("measure_value::bigint", "BIGINT"),
        ("measure_value::double", "DOUBLE"),
        ("measure_value::boolean", "BOOLEAN"),
        ("measure_value::varchar", "VARCHAR"),
        ("measure_value::timestamp", "TIMESTAMP"),
    ]

    for column_name, measure_type in typed_measure_columns:
        value = row.get(column_name)
        if value is not None:
            return to_measure_value(value, measure_type), measure_type

    generic_measure = row.get("measure_value")
    if generic_measure is None:
        return None, None

    if isinstance(generic_measure, bool):
        return to_measure_value(generic_measure, "BOOLEAN"), "BOOLEAN"
    if isinstance(generic_measure, int):
        return to_measure_value(generic_measure, "BIGINT"), "BIGINT"
    if isinstance(generic_measure, float):
        return to_measure_value(generic_measure, "DOUBLE"), "DOUBLE"

    return str(generic_measure), "VARCHAR"


def is_dimension_field(field_name: str) -> bool:
    ignored_fields = {
        "time",
        "time_ns",
        "measure_name",
        "measure_value",
        "version",
    }
    return field_name not in ignored_fields and not field_name.startswith(
        "measure_value::"
    )


def build_record(
    row: Dict[str, Any], target_location_id: str
) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    time_ns = row.get("time_ns")
    if time_ns is None:
        return None, "missing time_ns"

    measure_name = row.get("measure_name")
    if not measure_name:
        return None, "missing measure_name"

    measure_value, measure_type = infer_measure_from_row(row)
    if measure_value is None or measure_type is None:
        return None, "missing supported measure_value"

    dimensions: List[Dict[str, str]] = []
    for key, value in row.items():
        if not is_dimension_field(key) or value is None:
            continue
        if isinstance(value, (dict, list, tuple, set)):
            continue

        dimension_value = target_location_id if key == "location_id" else str(value)
        dimensions.append({"Name": key, "Value": dimension_value})

    if not any(dimension["Name"] == "location_id" for dimension in dimensions):
        dimensions.append({"Name": "location_id", "Value": target_location_id})

    record = {
        "Dimensions": dimensions,
        "MeasureName": str(measure_name),
        "MeasureValue": measure_value,
        "MeasureValueType": measure_type,
        "Time": str(int(time_ns)),
        "TimeUnit": "NANOSECONDS",
    }
    return record, None


def chunked(records: List[Dict[str, Any]], size: int) -> Iterable[List[Dict[str, Any]]]:
    for index in range(0, len(records), size):
        yield records[index : index + size]


def query_all_rows(
    query_client: Any, query_string: str
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    next_token: Optional[str] = None
    all_rows: List[Dict[str, Any]] = []
    column_info: List[Dict[str, Any]] = []
    page_number = 0

    while True:
        query_kwargs: Dict[str, Any] = {"QueryString": query_string}
        if next_token:
            query_kwargs["NextToken"] = next_token

        response = query_client.query(**query_kwargs)
        if not column_info:
            column_info = response.get("ColumnInfo", [])

        page_rows = response.get("Rows", [])
        all_rows.extend(page_rows)

        page_number += 1
        print(f"Fetched page {page_number} ({len(page_rows)} rows)")

        next_token = response.get("NextToken")
        if not next_token:
            break

    return column_info, all_rows


def query_row_count(query_client: Any, location_id: str) -> int:
    response = query_client.query(QueryString=build_location_count_query(location_id))
    rows = response.get("Rows", [])
    if not rows:
        return 0
    return int(rows[0]["Data"][0]["ScalarValue"])


def query_time_range(
    query_client: Any, location_id: str
) -> Tuple[Optional[int], Optional[int]]:
    response = query_client.query(QueryString=build_time_range_query(location_id))
    rows = response.get("Rows", [])
    if not rows:
        return None, None

    data = rows[0].get("Data", [])
    min_value = data[0].get("ScalarValue") if len(data) > 0 else None
    max_value = data[1].get("ScalarValue") if len(data) > 1 else None
    return (
        int(min_value) if min_value is not None else None,
        int(max_value) if max_value is not None else None,
    )


def write_records(write_client: Any, records: List[Dict[str, Any]]) -> Tuple[int, int]:
    written_count = 0
    failed_count = 0

    for batch_index, batch in enumerate(chunked(records, BATCH_SIZE), start=1):
        try:
            response = write_client.write_records(
                DatabaseName=DATABASE_NAME,
                TableName=TABLE_NAME,
                Records=batch,
            )
            written_count += len(batch)
            if batch_index <= 3 or batch_index % 500 == 0:
                print(
                    "Batch "
                    f"{batch_index}: write acknowledged for {len(batch)} record(s). "
                    f"Response: {response}"
                )
        except write_client.exceptions.RejectedRecordsException as exc:
            rejected_records = exc.response.get("RejectedRecords", [])
            rejected_count = len(rejected_records)
            written_count += len(batch) - rejected_count
            failed_count += rejected_count
            print(
                f"Batch {batch_index}: {rejected_count}/{len(batch)} rejected records"
            )
            for rejected in rejected_records[:5]:
                print(f"Batch {batch_index}: rejected detail {rejected}")
        except (ClientError, BotoCoreError) as exc:
            failed_count += len(batch)
            print(f"Batch {batch_index}: failed to write batch ({exc})")

        if batch_index % 10 == 0:
            processed = batch_index * BATCH_SIZE
            print(f"Write progress: {processed}/{len(records)} attempted")

    return written_count, failed_count


def create_aws_session() -> Session:
    if AWS_PROFILE:
        return Session(profile_name=AWS_PROFILE)
    return Session()


def assert_timestream_access(session: Session, query_client: Any) -> Dict[str, str]:
    identity = session.client("sts").get_caller_identity()
    account = identity.get("Account", "unknown")
    arn = identity.get("Arn", "unknown")

    try:
        query_client.describe_endpoints()
        return {"account": account, "arn": arn}
    except query_client.exceptions.AccessDeniedException as exc:
        available_profiles = Session().available_profiles
        profiles_text = ", ".join(available_profiles) if available_profiles else "none"
        message = (
            "Timestream access denied for the current AWS identity.\n"
            f"Account: {account}\n"
            f"ARN: {arn}\n"
            f"Region: {AWS_REGION}\n"
            f"Configured profile: {AWS_PROFILE or 'default'}\n"
            f"Available local profiles: {profiles_text}\n"
            "Use a profile that has Timestream LiveAnalytics access, for example:\n"
            "  $env:TIMESTREAM_AWS_PROFILE='work'\n"
            "Then rerun: python .\\copy_timestream_data\\main.py\n"
            f"Original error: {exc}"
        )
        raise RuntimeError(message) from exc


def describe_timestream_destination(write_client: Any) -> Dict[str, Any]:
    try:
        database_description = write_client.describe_database(
            DatabaseName=DATABASE_NAME
        ).get("Database", {})
        table_description = write_client.describe_table(
            DatabaseName=DATABASE_NAME,
            TableName=TABLE_NAME,
        ).get("Table", {})
    except (ClientError, BotoCoreError) as exc:
        raise RuntimeError(
            "Unable to describe the configured Timestream destination. "
            f"Database={DATABASE_NAME}, Table={TABLE_NAME}, Region={AWS_REGION}. "
            f"Original error: {exc}"
        ) from exc

    retention = table_description.get("RetentionProperties", {})
    magnetic_store = table_description.get("MagneticStoreWriteProperties", {})
    print(
        "Destination check: "
        f"database={database_description.get('DatabaseName', DATABASE_NAME)}, "
        f"table={table_description.get('TableName', TABLE_NAME)}, "
        f"memory_hours={retention.get('MemoryStoreRetentionPeriodInHours', 'unknown')}, "
        f"magnetic_days={retention.get('MagneticStoreRetentionPeriodInDays', 'unknown')}, "
        f"magnetic_writes={'enabled' if magnetic_store.get('EnableMagneticStoreWrites') else 'disabled'}"
    )
    return table_description


def format_ns_timestamp(time_ns: Optional[int]) -> str:
    if time_ns is None:
        return "unknown"
    return datetime.fromtimestamp(time_ns / 1_000_000_000, tz=timezone.utc).isoformat()


def log_source_time_range_and_retention(
    query_client: Any, table_description: Dict[str, Any], source_location_id: str
) -> None:
    min_time_ns, max_time_ns = query_time_range(query_client, source_location_id)
    print(
        "Source time range: "
        f"min={format_ns_timestamp(min_time_ns)}, max={format_ns_timestamp(max_time_ns)}"
    )

    memory_hours = table_description.get("RetentionProperties", {}).get(
        "MemoryStoreRetentionPeriodInHours"
    )
    magnetic_enabled = table_description.get("MagneticStoreWriteProperties", {}).get(
        "EnableMagneticStoreWrites"
    )

    if max_time_ns is None or not memory_hours:
        return

    memory_cutoff = datetime.now(timezone.utc) - timedelta(hours=int(memory_hours))
    latest_source_time = datetime.fromtimestamp(
        max_time_ns / 1_000_000_000, tz=timezone.utc
    )

    if latest_source_time < memory_cutoff:
        print(
            "Retention warning: the newest source record is older than the memory-store retention window. "
            f"New writes will rely on magnetic store ingestion ({'enabled' if magnetic_enabled else 'disabled'}), "
            "which can delay visibility after write acknowledgement."
        )


def log_sample_records(records_to_write: List[Dict[str, Any]]) -> None:
    sample_indexes = [0]
    if len(records_to_write) > 1:
        sample_indexes.append(len(records_to_write) - 1)

    for sample_index in sample_indexes:
        record = records_to_write[sample_index]
        location_id = next(
            (
                dimension["Value"]
                for dimension in record.get("Dimensions", [])
                if dimension.get("Name") == "location_id"
            ),
            "missing",
        )
        print(
            "Sample record "
            f"{sample_index + 1}: location_id={location_id}, "
            f"measure_name={record['MeasureName']}, "
            f"measure_type={record['MeasureValueType']}, "
            f"time_ns={record['Time']}"
        )


def verify_target_records(
    query_client: Any,
    target_location_id: str,
    sample_record: Dict[str, Any],
    retry_delays_seconds: List[int],
) -> Tuple[int, bool]:
    target_count = 0
    sample_found = False
    sample_query = build_sample_record_query(sample_record)

    for attempt_index, delay_seconds in enumerate(retry_delays_seconds, start=1):
        if delay_seconds > 0:
            print(
                f"Verification attempt {attempt_index}: waiting {delay_seconds}s before query"
            )
            time.sleep(delay_seconds)

        target_count = query_row_count(query_client, target_location_id)
        sample_response = query_client.query(QueryString=sample_query)
        sample_found = bool(sample_response.get("Rows"))
        print(
            f"Verification attempt {attempt_index}: target_count={target_count}, sample_found={sample_found}"
        )

        if target_count > 0 or sample_found:
            return target_count, sample_found

    return target_count, sample_found


def main() -> None:
    session = create_aws_session()
    query_client = session.client("timestream-query", region_name=AWS_REGION)
    write_client = session.client("timestream-write", region_name=AWS_REGION)

    identity = assert_timestream_access(session, query_client)
    print(
        f"Using AWS account {identity['account']} in {AWS_REGION} "
        f"(profile: {AWS_PROFILE or 'default'})"
    )
    print(
        f"Resolved configuration: env_file={ENV_FILE}, database={DATABASE_NAME}, table={TABLE_NAME}"
    )
    table_description = describe_timestream_destination(write_client)

    source_query = build_source_query(SOURCE_LOCATION_ID)
    print(f"Running source query for location_id={SOURCE_LOCATION_ID}")

    source_count_before = query_row_count(query_client, SOURCE_LOCATION_ID)
    target_count_before = query_row_count(query_client, TARGET_LOCATION_ID)
    print(f"Source rows before copy: {source_count_before}")
    print(f"Target rows before copy: {target_count_before}")
    log_source_time_range_and_retention(
        query_client, table_description, SOURCE_LOCATION_ID
    )

    column_info, raw_rows = query_all_rows(query_client, source_query)
    normalized_rows = normalize_rows(column_info, raw_rows)
    print(f"Normalized {len(normalized_rows)} row(s)")

    records_to_write: List[Dict[str, Any]] = []
    skipped_count = 0
    for row_index, row in enumerate(normalized_rows, start=1):
        record, skip_reason = build_record(row, TARGET_LOCATION_ID)
        if record is None:
            skipped_count += 1
            print(f"Skipped row {row_index}: {skip_reason}")
            continue
        records_to_write.append(record)

    print(
        f"Prepared {len(records_to_write)} record(s) for write. Skipped {skipped_count} row(s)."
    )

    if not records_to_write:
        print("No writable records found. Exiting without writes.")
        return

    log_sample_records(records_to_write)

    written_count, failed_count = write_records(write_client, records_to_write)

    target_count_after, sample_found = verify_target_records(
        query_client,
        TARGET_LOCATION_ID,
        records_to_write[0],
        retry_delays_seconds=[0, 5, 15],
    )
    print("Copy complete.")
    print(f"Written: {written_count}")
    print(f"Failed: {failed_count}")
    print(f"Skipped: {skipped_count}")
    print(f"Target rows after copy: {target_count_after}")
    print(f"Sample record visible after copy: {sample_found}")


if __name__ == "__main__":
    main()
