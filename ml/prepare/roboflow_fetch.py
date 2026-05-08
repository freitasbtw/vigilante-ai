"""Download multiple Roboflow Universe datasets via the official SDK.

Why this and not raw curl: the SDK authenticates with your API key, so it
fetches private + unlisted versions, and raises a clear error if a slug
no longer exists (instead of returning a misleading HTML page).

Usage:
    export ROBOFLOW_API_KEY=<your-key>
    python -m ml.prepare.roboflow_fetch \
        https://universe.roboflow.com/foo/bar/dataset/3 \
        https://universe.roboflow.com/baz/qux/dataset/1

Or read URLs one-per-line from a file:
    python -m ml.prepare.roboflow_fetch --from-file my_urls.txt

Output goes to ml/datasets/<project-slug>/ in YOLOv8 format.
"""

from __future__ import annotations

import argparse
import logging
import os
import re
import sys
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("roboflow-fetch")

# Accept several URL shapes Roboflow uses in the wild
_URL_RE = re.compile(
    r"https?://universe\.roboflow\.com/"
    r"(?P<workspace>[^/]+)/(?P<project>[^/]+)"
    r"(?:/dataset/(?P<version>\d+))?"
    r"(?:/?(?:browse|model|deploy)?)?"
    r"/?$"
)


def parse_url(url: str) -> tuple[str, str, int]:
    """Returns (workspace, project, version). Defaults version to 1 if absent."""
    m = _URL_RE.match(url.strip())
    if not m:
        raise ValueError(f"Cannot parse Roboflow URL: {url}")
    workspace = m.group("workspace")
    project = m.group("project")
    version = int(m.group("version") or 1)
    return workspace, project, version


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Download Roboflow Universe datasets in bulk")
    p.add_argument("urls", nargs="*", help="Roboflow Universe URLs")
    p.add_argument("--from-file", type=Path, help="Read URLs from a file (one per line)")
    p.add_argument(
        "--out-root",
        type=Path,
        default=Path("ml/datasets"),
        help="Where to drop each downloaded project",
    )
    p.add_argument(
        "--format",
        type=str,
        default="yolov8",
        help="Roboflow export format (default: yolov8)",
    )
    return p.parse_args()


def main() -> None:
    args = parse_args()
    api_key = os.environ.get("ROBOFLOW_API_KEY")
    if not api_key:
        sys.exit("ERROR: set ROBOFLOW_API_KEY first (https://app.roboflow.com/settings/api)")

    urls: list[str] = list(args.urls)
    if args.from_file:
        urls.extend(
            line.strip()
            for line in args.from_file.read_text().splitlines()
            if line.strip() and not line.startswith("#")
        )
    if not urls:
        sys.exit("No URLs provided. Pass them as args or via --from-file")

    try:
        from roboflow import Roboflow
    except ImportError:
        sys.exit("Install the SDK first: pip install roboflow")

    rf = Roboflow(api_key=api_key)
    args.out_root.mkdir(parents=True, exist_ok=True)

    for url in urls:
        try:
            workspace, project, version = parse_url(url)
        except ValueError as exc:
            logger.error("Skipping invalid URL: %s", exc)
            continue

        target_dir = args.out_root / project
        if target_dir.exists() and any(target_dir.iterdir()):
            logger.info("Already present, skipping: %s", target_dir)
            continue

        logger.info("Fetching %s/%s version=%d", workspace, project, version)
        try:
            ws = rf.workspace(workspace)
            proj = ws.project(project)
            ver = proj.version(version)
            ds = ver.download(args.format, location=str(target_dir))
            logger.info("Downloaded %s → %s", project, ds.location)
        except Exception as exc:
            logger.error("Failed %s/%s v%d: %s", workspace, project, version, exc)


if __name__ == "__main__":
    main()
