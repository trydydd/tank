#!/usr/bin/env bash
set -euo pipefail

usage() {
    cat <<EOF
Usage: $(basename "$0") <url> <name@version> [options]

Mirror an HTML documentation site with wget and build a synd .ctx pack.

Use this for packages whose docs have no llms.txt or llms-full.txt. For docs
that do provide those files, use build-pack.sh instead.

Arguments:
  url           Root URL of the documentation site to mirror
  name@version  Pack identifier, e.g. requests@2.34.2

Options:
  --output <dir>           Directory to write the .ctx file (default: ./packs)
  --mirror-dir <dir>       Directory to write mirrored HTML (default: ./<name>-html)
  --exclude-dir <name>     Subdirectory name to delete before building (repeatable)
  --keep-mirror            Do not delete the mirror directory after building
  -h, --help               Show this help message

Noise directories excluded by default (pass --exclude-dir to add more):
  _modules  genindex  search

Examples:
  $(basename "$0") https://requests.readthedocs.io/en/latest/ requests@2.34.2
  $(basename "$0") https://click.palletsprojects.com/en/stable/ click@8.1.8 --output ./releases
  $(basename "$0") https://docs.pytest.org/en/stable/ pytest@8.3.5 \\
      --exclude-dir changelog --exclude-dir reference/changelog
EOF
}

# Defaults
OUTPUT_DIR="./packs"
MIRROR_DIR=""
KEEP_MIRROR=false
EXTRA_EXCLUDES=()
# Directories that are readthedocs boilerplate, not documentation content
DEFAULT_EXCLUDES=(_modules genindex search)

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
        --mirror-dir)
            MIRROR_DIR="$2"
            shift 2
            ;;
        --exclude-dir)
            EXTRA_EXCLUDES+=("$2")
            shift 2
            ;;
        --keep-mirror)
            KEEP_MIRROR=true
            shift
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
    echo "error: pack name must be in name@version format (e.g. requests@2.34.2)" >&2
    exit 1
fi

PACK_BASENAME="${PACK_NAME%%@*}"

if [[ -z "$MIRROR_DIR" ]]; then
    MIRROR_DIR="./${PACK_BASENAME}-html"
fi

# Mirror the documentation site
echo "Mirroring $URL → $MIRROR_DIR ..."
wget --mirror -p --html-extension --convert-links \
     -e robots=off --no-parent \
     -P "$MIRROR_DIR" \
     "$URL" 2>&1 | grep -v "^$" | tail -5

# Derive the mirrored content path from the URL hostname + path
URL_HOST=$(python3 -c "from urllib.parse import urlparse; u=urlparse('$URL'); print(u.netloc)")
URL_PATH=$(python3 -c "from urllib.parse import urlparse; u=urlparse('$URL'); print(u.path.lstrip('/'))")
SOURCE_DIR="$MIRROR_DIR/$URL_HOST/$URL_PATH"

if [[ ! -d "$SOURCE_DIR" ]]; then
    echo "error: expected mirror directory not found: $SOURCE_DIR" >&2
    exit 1
fi

HTML_COUNT=$(find "$SOURCE_DIR" -name "*.html" | wc -l | tr -d ' ')
echo "Downloaded $HTML_COUNT HTML files to $SOURCE_DIR"

# Remove noise directories
ALL_EXCLUDES=("${DEFAULT_EXCLUDES[@]}" "${EXTRA_EXCLUDES[@]}")
for dir in "${ALL_EXCLUDES[@]}"; do
    TARGET="$SOURCE_DIR/$dir"
    if [[ -d "$TARGET" ]]; then
        echo "Removing noise directory: $dir/"
        rm -rf "$TARGET"
    fi
done

# Build the pack
mkdir -p "$OUTPUT_DIR"
echo "Building $PACK_NAME ..."
synd build "$PACK_NAME" --source "$SOURCE_DIR" --output "$OUTPUT_DIR"

if [[ "$KEEP_MIRROR" = false ]]; then
    echo "Cleaning up mirror directory ..."
    rm -rf "$MIRROR_DIR"
fi

echo "Done: $OUTPUT_DIR/$PACK_NAME.ctx"
