#!/usr/bin/env bash
# Merge admin/supervisor feedback exports into the YOLO training dataset.
#
# Source layout (written by RetrainingExporter):
#   ml/data/feedback/confirmed/<alert_id>.jpg + .txt   ← positives
#   ml/data/feedback/rejected/<alert_id>.jpg  + .txt   ← negatives (empty .txt)
#
# Target layout (the existing 2-class canteiro split):
#   ml/datasets/merged/images/train/<alert_id>.jpg
#   ml/datasets/merged/labels/train/<alert_id>.txt
#
# After merging, files are MOVED to ml/data/feedback/merged/<decision>/<alert_id>.{jpg,txt}
# so re-running this script is idempotent.
#
# Usage:
#   ml/scripts/merge_feedback.sh [--dataset DATASET_DIR] [--dry-run]
#
# Exits non-zero if anything goes wrong; prints a summary at the end.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
DATASET_DIR="${REPO_ROOT}/ml/datasets/merged"
DRY_RUN=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --dataset) DATASET_DIR="$2"; shift 2 ;;
    --dry-run) DRY_RUN=1; shift ;;
    -h|--help)
      sed -n '2,/^$/p' "$0" | sed 's/^# \{0,1\}//'
      exit 0
      ;;
    *)
      echo "Unknown arg: $1" >&2
      exit 2
      ;;
  esac
done

FEEDBACK_DIR="${REPO_ROOT}/ml/data/feedback"
IMG_OUT="${DATASET_DIR}/images/train"
LBL_OUT="${DATASET_DIR}/labels/train"

if [[ ! -d "${FEEDBACK_DIR}" ]]; then
  echo "Feedback dir missing: ${FEEDBACK_DIR}" >&2
  exit 1
fi

mkdir -p "${IMG_OUT}" "${LBL_OUT}" "${FEEDBACK_DIR}/merged/confirmed" "${FEEDBACK_DIR}/merged/rejected"

merged_count=0
skipped_count=0

merge_decision() {
  local decision="$1"
  local src_dir="${FEEDBACK_DIR}/${decision}"
  local archive_dir="${FEEDBACK_DIR}/merged/${decision}"

  shopt -s nullglob
  for img in "${src_dir}"/*.jpg; do
    local alert_id
    alert_id="$(basename "${img}" .jpg)"
    local lbl="${src_dir}/${alert_id}.txt"
    if [[ ! -f "${lbl}" ]]; then
      echo "  skip ${alert_id}: missing label .txt" >&2
      skipped_count=$((skipped_count + 1))
      continue
    fi

    if [[ "${DRY_RUN}" == "1" ]]; then
      echo "  would merge [${decision}] ${alert_id}"
    else
      cp -f "${img}" "${IMG_OUT}/${alert_id}.jpg"
      cp -f "${lbl}" "${LBL_OUT}/${alert_id}.txt"
      mv -f "${img}" "${archive_dir}/${alert_id}.jpg"
      mv -f "${lbl}" "${archive_dir}/${alert_id}.txt"
    fi
    merged_count=$((merged_count + 1))
  done
  shopt -u nullglob
}

echo "Merging feedback exports into ${DATASET_DIR}"
merge_decision "confirmed"
merge_decision "rejected"

echo
echo "Summary:"
echo "  merged:  ${merged_count}"
echo "  skipped: ${skipped_count}"
echo
if [[ "${DRY_RUN}" == "1" ]]; then
  echo "(dry run — no files moved)"
else
  echo "Files archived under ${FEEDBACK_DIR}/merged/{confirmed,rejected}/"
  echo "Re-run training (e.g. ml/run_pipeline.sh) when you have enough new"
  echo "samples to justify a fine-tune."
fi
