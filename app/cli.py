from __future__ import annotations

import argparse
import re

from sqlalchemy import select

from app import models
from app.database import SessionLocal, init_db
from app.services.brand_service import create_brand
from app.services.jobs import process_pending_jobs


def slugify(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")


def cmd_init_db(_: argparse.Namespace) -> None:
    init_db()
    print("Database initialized.")


def cmd_create_brand(args: argparse.Namespace) -> None:
    with SessionLocal() as db:
        payload = {
            "name": args.name,
            "slug": args.slug or slugify(args.name),
            "description": args.description,
            "default_language": args.default_language,
            "tone_name": args.tone_name,
            "tone_instructions": args.tone_instructions,
            "fallback_handoff_message": args.fallback_handoff_message,
            "public_reply_guidelines": args.public_reply_guidelines,
            "settings": {},
        }
        brand, api_key = create_brand(db, payload)
        print(f"Brand created: id={brand.id} slug={brand.slug}")
        print(f"API key: {api_key}")


def cmd_run_jobs(args: argparse.Namespace) -> None:
    with SessionLocal() as db:
        jobs = process_pending_jobs(db, args.limit)
        print(f"Processed {len(jobs)} jobs.")
        for job in jobs:
            print(f"- job={job.id} kind={job.kind} status={job.status}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="B2B AI Support API utilities")
    subparsers = parser.add_subparsers(dest="command", required=True)

    init_parser = subparsers.add_parser("init-db", help="Create all database tables")
    init_parser.set_defaults(func=cmd_init_db)

    brand_parser = subparsers.add_parser("create-brand", help="Create a brand and print its API key")
    brand_parser.add_argument("--name", required=True)
    brand_parser.add_argument("--slug")
    brand_parser.add_argument("--description")
    brand_parser.add_argument("--default-language", default="en")
    brand_parser.add_argument("--tone-name", default="Helpful sales assistant")
    brand_parser.add_argument("--tone-instructions", default="")
    brand_parser.add_argument(
        "--fallback-handoff-message",
        default="A human teammate will continue this conversation shortly.",
    )
    brand_parser.add_argument("--public-reply-guidelines")
    brand_parser.set_defaults(func=cmd_create_brand)

    jobs_parser = subparsers.add_parser("run-jobs", help="Process pending async jobs")
    jobs_parser.add_argument("--limit", type=int, default=10)
    jobs_parser.set_defaults(func=cmd_run_jobs)

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
