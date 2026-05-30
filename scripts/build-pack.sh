#!/usr/bin/env bash
set -euo pipefail

usage() {
    cat <<EOF
Usage: $(basename "$0") <url> <name@version> [--output <dir>]

Download an llms-full.txt from a URL and build a Synaptic Drift .ctx pack.

Arguments:
  url           URL of the llms-full.txt to fetch
  name@version  Pack identifier, e.g. mcp@2025-11-25 or fastmcp@3.3.0

Options:
  --output <dir>  Directory to write the .ctx file (default: ./packs)
  -h, --help      Show this help message

Examples:
  $(basename "$0") https://modelcontextprotocol.io/llms-full.txt mcp@2025-11-25
  $(basename "$0") https://gofastmcp.com/llms-full.txt fastmcp@3.3.0 --output ./releases
EOF
}

# Defaults
OUTPUT_DIR="./packs"

# Parse arguments
URL=""
PACK_NAME=""

while [[ $# -gt 0 ]]; do
    case "$1" in
        -h|--help)
            usage
            exit 0
            ;;
        --output)
            OUTPUT_DIR="$2"
            shift 2
            ;;
        -*)
            echo "error: unknown option: $1" >&2
            usage >&2
            exit 1
            ;;
        *)
            if [[ -z "$URL" ]]; then
                URL="$1"
            elif [[ -z "$PACK_NAME" ]]; then
                PACK_NAME="$1"
            else
                echo "error: unexpected argument: $1" >&2
                usage >&2
                exit 1
            fi
            shift
            ;;
    esac
done

if [[ -z "$URL" || -z "$PACK_NAME" ]]; then
    echo "error: url and name@version are required" >&2
    usage >&2
    exit 1
fi

if [[ ! "$PACK_NAME" =~ ^[a-zA-Z0-9_.-]+@[a-zA-Z0-9_.-]+$ ]]; then
    echo "error: pack name must be in name@version format (e.g. mcp@2025-11-25)" >&2
    exit 1
fi

# Derive the name portion for the temp filename
PACK_BASENAME="${PACK_NAME%%@*}"

WORK_DIR=$(mktemp -d)
trap 'rm -rf "$WORK_DIR"' EXIT

SOURCE_FILE="$WORK_DIR/$PACK_BASENAME.md"

echo "Downloading $URL ..."
curl --fail --silent --show-error --location -o "$SOURCE_FILE" "$URL"
echo "Saved to $SOURCE_FILE ($(wc -c < "$SOURCE_FILE" | tr -d ' ') bytes)"

mkdir -p "$OUTPUT_DIR"

echo "Building $PACK_NAME ..."
synd build "$PACK_NAME" --source "$WORK_DIR" --output "$OUTPUT_DIR"

echo "Done: $OUTPUT_DIR/$PACK_NAME.ctx"
