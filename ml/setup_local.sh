#!/usr/bin/env bash
# One-shot: create local virtualenv with PyTorch (CUDA 12.1) + ultralytics.
# Targets a recent NVIDIA GPU on Linux (RTX 4070 Super tested).
#
# Usage:
#   bash ml/setup_local.sh
#   source ml/.venv/bin/activate
#   nvidia-smi   # confirm GPU is visible
#   python -c "import torch; print(torch.cuda.is_available(), torch.cuda.get_device_name(0))"

set -euo pipefail

cd "$(dirname "$0")"

if ! command -v python3.11 >/dev/null 2>&1 && ! command -v python3.10 >/dev/null 2>&1; then
  echo "WARN: python 3.10 or 3.11 recommended for torch/ultralytics. Using $(python3 --version)."
fi

PY=python3.11
command -v $PY >/dev/null 2>&1 || PY=python3.10
command -v $PY >/dev/null 2>&1 || PY=python3

$PY -m venv .venv
source .venv/bin/activate
pip install -U pip wheel

# CUDA 12.1 build of PyTorch — works with Ada Lovelace (RTX 40 series)
pip install torch torchvision --index-url https://download.pytorch.org/whl/cu121

pip install \
  "ultralytics>=8.1.0" \
  "albumentations>=1.4.0" \
  "opencv-python-headless>=4.9.0" \
  "pyyaml>=6.0" \
  "numpy>=1.26.0" \
  "roboflow>=1.1.0" \
  "onnx>=1.15.0" \
  "onnxruntime-gpu>=1.17.0"

echo
echo "==================================================================="
echo " Done. Activate with:  source ml/.venv/bin/activate"
echo " Verify CUDA:          python -c 'import torch; print(torch.cuda.is_available())'"
echo "==================================================================="
