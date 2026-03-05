#!/usr/bin/env bash
# Download TinyLlama GGUF model (~669 MB)
set -euo pipefail
MODEL_DIR="./models"
MODEL_FILE="tinyllama-1.1b-chat-v1.0.Q4_K_M.gguf"
HF_REPO="TheBloke/TinyLlama-1.1B-Chat-v1.0-GGUF"
URL="https://huggingface.co/${HF_REPO}/resolve/main/${MODEL_FILE}"
mkdir -p "$MODEL_DIR"
if [ -f "${MODEL_DIR}/${MODEL_FILE}" ]; then
  echo "✓ Model already exists: ${MODEL_DIR}/${MODEL_FILE}"; exit 0
fi
echo "Downloading TinyLlama (~669 MB) …"
if command -v huggingface-cli &>/dev/null; then
  huggingface-cli download "$HF_REPO" "$MODEL_FILE" --local-dir "$MODEL_DIR"
elif command -v wget &>/dev/null; then
  wget -O "${MODEL_DIR}/${MODEL_FILE}" "$URL" --progress=bar:force
else
  curl -L "$URL" -o "${MODEL_DIR}/${MODEL_FILE}" --progress-bar
fi
echo "✓ Saved to ${MODEL_DIR}/${MODEL_FILE}"
