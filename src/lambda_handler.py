"""
ETL Lambda handler.

Triggered by S3 ObjectCreated events under the `raw/` prefix.
Parses a CSV file, validates each row, writes valid rows to DynamoDB,
sends invalid rows to an SQS dead-letter queue, and copies the source
file into `processed/` or `rejected/` depending on outcome.
"""
import csv
import io
import json
import logging
import os
from datetime import datetime, timezone

import boto3

logger = logging.getLogger()
logger.setLevel(logging.INFO)

s3 = boto3.client("s3")
dynamodb = boto3.resource("dynamodb")
sqs = boto3.client("sqs")

TABLE_NAME = os.environ.get("TABLE_NAME", "orders-table")
DLQ_URL = os.environ.get("DLQ_URL")

REQUIRED_FIELDS = ["order_id", "customer_name", "amount", "order_date"]


def validate_row(row: dict) -> list[str]:
    """Return a list of validation error strings; empty list means valid."""
    errors = []
    for field in REQUIRED_FIELDS:
        if not row.get(field):
            errors.append(f"missing field: {field}")

    if row.get("amount"):
        try:
            amount = float(row["amount"])
            if amount < 0:
                errors.append("amount must be non-negative")
        except ValueError:
            errors.append("amount is not a valid number")

    return errors


def transform_row(row: dict) -> dict:
    """Normalize a valid row into the shape stored in DynamoDB."""
    return {
        "order_id": row["order_id"].strip(),
        "customer_name": row["customer_name"].strip(),
        "amount": str(round(float(row["amount"]), 2)),
        "order_date": row["order_date"].strip(),
        "processed_at": datetime.now(timezone.utc).isoformat(),
    }


def handler(event, context):
    table = dynamodb.Table(TABLE_NAME)
    results = {"processed": 0, "rejected": 0, "files": []}

    for record in event.get("Records", []):
        bucket = record["s3"]["bucket"]["name"]
        key = record["s3"]["object"]["key"]
        logger.info("Processing s3://%s/%s", bucket, key)

        obj = s3.get_object(Bucket=bucket, Key=key)
        content = obj["Body"].read().decode("utf-8")
        reader = csv.DictReader(io.StringIO(content))

        valid_rows = []
        invalid_rows = []

        for row in reader:
            errors = validate_row(row)
            if errors:
                invalid_rows.append({"row": row, "errors": errors})
            else:
                valid_rows.append(transform_row(row))

        # Write valid rows to DynamoDB
        for item in valid_rows:
            table.put_item(Item=item)

        # Send invalid rows to the dead-letter queue for later inspection
        for bad in invalid_rows:
            if DLQ_URL:
                sqs.send_message(QueueUrl=DLQ_URL, MessageBody=json.dumps(bad))

        # Move the source file to processed/ or rejected/ based on outcome
        filename = key.split("/")[-1]
        dest_prefix = "rejected" if invalid_rows and not valid_rows else "processed"
        dest_key = f"{dest_prefix}/{filename}"
        s3.copy_object(Bucket=bucket, CopySource={"Bucket": bucket, "Key": key}, Key=dest_key)
        s3.delete_object(Bucket=bucket, Key=key)

        results["processed"] += len(valid_rows)
        results["rejected"] += len(invalid_rows)
        results["files"].append(key)

        logger.info(
            "Finished %s: %d valid, %d rejected",
            key, len(valid_rows), len(invalid_rows),
        )

    return {"statusCode": 200, "body": json.dumps(results)}
