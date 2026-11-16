"""
Copy the API keys the ingestion jobs need from .env to AWS SSM Parameter Store (SecureString,
AWS-managed key aws/ssm), as /asap-chem-hub/<NAME>. Terraform only refers to these names; it never
holds the values, so they stay out of Terraform state.

Values are sent by boto3 directly - never printed, never on a command line, never in a temp file.
The database password is NOT copied: on AWS the app uses RDS IAM authentication.

Usage (from the project folder; uses your current AWS login)
    python scripts/put_ssm_params.py             # dry run: which names would be written, no values
    python scripts/put_ssm_params.py --apply     # create / overwrite the parameters
"""

import argparse
import os
import sys

from dotenv import dotenv_values

PREFIX = "/asap-chem-hub/"
NAMES = ["EPO_KEY", "EPO_SECRET", "SPRINGER_META_KEY", "SPRINGER_OA_KEY", "CROSSREF_MAILTO"]
REGION = "us-east-2"          # the project account's home region (same as Terraform var.region)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--apply", action="store_true", help="write the parameters (default: dry run)")
    args = ap.parse_args()

    env = dotenv_values(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env"))
    missing = [n for n in NAMES if not (env.get(n) or "").strip()]
    if missing:
        sys.exit(f"Missing or empty in .env: {missing}. Nothing written.")
    for n in NAMES:
        print(f"  {PREFIX}{n}  (SecureString, {len(env[n].strip())} characters)")
    if not args.apply:
        print("Dry run: nothing written. Run with --apply to write.")
        return

    import boto3
    ssm = boto3.client("ssm", region_name=REGION)
    for n in NAMES:
        ssm.put_parameter(Name=PREFIX + n, Value=env[n].strip(), Type="SecureString", Overwrite=True,
                          Description="ASAP Chem Hub ingestion setting (from .env)")
        ssm.add_tags_to_resource(ResourceType="Parameter", ResourceId=PREFIX + n,
                                 Tags=[{"Key": "Project", "Value": "asap-chem-hub"}])
        print(f"  wrote {PREFIX}{n}")


if __name__ == "__main__":
    main()
