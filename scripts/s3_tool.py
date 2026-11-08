#!/usr/bin/env python3
"""Tiny S3 client for the host (boto3). Reads S3_ENDPOINT, AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY.

  s3_tool.py mb BUCKET [BUCKET ...]          create buckets (ignored if they exist)
  s3_tool.py put FILE BUCKET KEY             upload a file
  s3_tool.py put-dir DIR BUCKET PREFIX       upload every file in DIR under PREFIX/
  s3_tool.py get BUCKET KEY FILE             download an object
  s3_tool.py cat BUCKET KEY                  print an object to stdout
  s3_tool.py ls BUCKET [PREFIX]              list keys with sizes
"""
import os
import pathlib
import sys

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError


def client():
    return boto3.client(
        "s3",
        endpoint_url=os.environ["S3_ENDPOINT"],
        region_name="us-east-1",
        config=Config(s3={"addressing_style": "path"}, retries={"max_attempts": 5}),
    )


def main(argv):
    if len(argv) < 2:
        sys.exit(__doc__)
    cmd, args, s3 = argv[1], argv[2:], client()
    if cmd == "mb":
        for bucket in args:
            try:
                s3.create_bucket(Bucket=bucket)
                print(f"created bucket {bucket}")
            except ClientError as e:
                if e.response["Error"]["Code"] in ("BucketAlreadyOwnedByYou", "BucketAlreadyExists"):
                    print(f"bucket {bucket} already exists")
                else:
                    raise
    elif cmd == "put":
        path, bucket, key = args
        s3.upload_file(path, bucket, key)
        print(f"uploaded {path} -> s3://{bucket}/{key}")
    elif cmd == "put-dir":
        folder, bucket, prefix = pathlib.Path(args[0]), args[1], args[2].strip("/")
        for p in sorted(folder.rglob("*")):
            if p.is_file():
                key = f"{prefix}/{p.relative_to(folder).as_posix()}"
                s3.upload_file(str(p), bucket, key)
                print(f"uploaded {p} -> s3://{bucket}/{key}")
    elif cmd == "get":
        bucket, key, path = args
        s3.download_file(bucket, key, path)
    elif cmd == "cat":
        bucket, key = args
        sys.stdout.buffer.write(s3.get_object(Bucket=bucket, Key=key)["Body"].read())
    elif cmd == "ls":
        bucket = args[0]
        prefix = args[1] if len(args) > 1 else ""
        for page in s3.get_paginator("list_objects_v2").paginate(Bucket=bucket, Prefix=prefix):
            for obj in page.get("Contents", []):
                print(f"{obj['Size']:>12}  {obj['Key']}")
    else:
        sys.exit(__doc__)


if __name__ == "__main__":
    main(sys.argv)
