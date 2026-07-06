#!/usr/bin/env python3
"""A minimal CLI greeting tool."""

import argparse


def main():
    parser = argparse.ArgumentParser(description="Print a greeting.")
    parser.add_argument(
        "name",
        nargs="?",
        default="World",
        help="Name to greet (default: World)",
    )
    args = parser.parse_args()
    print(f"Hello, {args.name}!")


if __name__ == "__main__":
    main()
