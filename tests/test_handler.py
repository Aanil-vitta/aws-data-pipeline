"""
Unit tests for the ETL Lambda handler.

Uses moto to mock S3, DynamoDB, and SQS so these run entirely locally —
no AWS account or credentials required. This is what CI runs on every push.
"""
import json
import os

import boto3
import pytest
from moto import mock_aws

os.environ["TABLE_NAME"] = "test-orders"
os.environ["DLQ_URL"] = "https://sqs.us-east-1.amazonaws.com/123456789012/test-dlq"
os.environ.setdefault("AWS_DEFAULT_REGION", "us-east-1")
os.environ.setdefault("AWS_ACCESS_KEY_ID", "testing")
os.environ.setdefault("AWS_SECRET_ACCESS_KEY", "testing")
os.environ.setdefault("AWS_SECURITY_TOKEN", "testing")
os.environ.setdefault("AWS_SESSION_TOKEN", "testing")

from src.lambda_handler import handler, transform_row, validate_row  # noqa: E402

BUCKET = "test-bucket"
REGION = "us-east-1"


@pytest.fixture
def aws_env():
    with mock_aws():
        s3 = boto3.client("s3", region_name=REGION)
        s3.create_bucket(Bucket=BUCKET)

        dynamodb = boto3.resource("dynamodb", region_name=REGION)
        dynamodb.create_table(
            TableName="test-orders",
            KeySchema=[{"AttributeName": "order_id", "KeyType": "HASH"}],
            AttributeDefinitions=[{"AttributeName": "order_id", "AttributeType": "S"}],
            BillingMode="PAY_PER_REQUEST",
        )

        sqs = boto3.client("sqs", region_name=REGION)
        sqs.create_queue(QueueName="test-dlq")

        yield {"s3": s3, "dynamodb": dynamodb, "sqs": sqs}


def s3_event(key: str) -> dict:
    return {"Records": [{"s3": {"bucket": {"name": BUCKET}, "object": {"key": key}}}]}


# --- Pure function tests (no AWS needed at all) -----------------------------

def test_validate_row_valid():
    row = {"order_id": "1", "customer_name": "Alice", "amount": "10.50", "order_date": "2026-01-01"}
    assert validate_row(row) == []


def test_validate_row_missing_field():
    row = {"order_id": "1", "customer_name": "", "amount": "10.50", "order_date": "2026-01-01"}
    errors = validate_row(row)
    assert any("customer_name" in e for e in errors)


def test_validate_row_bad_amount():
    row = {"order_id": "1", "customer_name": "Alice", "amount": "not-a-number", "order_date": "2026-01-01"}
    errors = validate_row(row)
    assert any("amount" in e for e in errors)


def test_transform_row_rounds_amount():
    row = {"order_id": " 1 ", "customer_name": " Alice ", "amount": "10.567", "order_date": "2026-01-01"}
    result = transform_row(row)
    assert result["amount"] == "10.57"
    assert result["order_id"] == "1"


# --- End-to-end handler tests (mocked AWS) ----------------------------------

def test_handler_valid_rows_go_to_dynamodb(aws_env):
    csv_content = "order_id,customer_name,amount,order_date\n1,Alice,10.50,2026-01-01\n2,Bob,20.00,2026-01-02\n"
    aws_env["s3"].put_object(Bucket=BUCKET, Key="raw/orders.csv", Body=csv_content)

    result = handler(s3_event("raw/orders.csv"), None)
    body = json.loads(result["body"])

    assert body["processed"] == 2
    assert body["rejected"] == 0

    table = aws_env["dynamodb"].Table("test-orders")
    item = table.get_item(Key={"order_id": "1"})["Item"]
    assert item["customer_name"] == "Alice"


def test_handler_invalid_rows_go_to_dlq(aws_env):
    csv_content = "order_id,customer_name,amount,order_date\n,Alice,10.50,2026-01-01\n"
    aws_env["s3"].put_object(Bucket=BUCKET, Key="raw/bad.csv", Body=csv_content)

    result = handler(s3_event("raw/bad.csv"), None)
    body = json.loads(result["body"])

    assert body["processed"] == 0
    assert body["rejected"] == 1


def test_handler_moves_file_to_processed_prefix(aws_env):
    csv_content = "order_id,customer_name,amount,order_date\n1,Alice,10.50,2026-01-01\n"
    aws_env["s3"].put_object(Bucket=BUCKET, Key="raw/orders.csv", Body=csv_content)

    handler(s3_event("raw/orders.csv"), None)

    objects = aws_env["s3"].list_objects_v2(Bucket=BUCKET).get("Contents", [])
    keys = [o["Key"] for o in objects]
    assert "processed/orders.csv" in keys
    assert "raw/orders.csv" not in keys
