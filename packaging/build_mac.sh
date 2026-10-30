#!/bin/bash
# 在 macOS（Apple Silicon）上打 ZhangguiPet.app 测试包：onedir .app + zip，未签名、未公证（ad-hoc 签名）。
#   packaging/build_mac.sh [venv 的 python 路径]     默认 ../.venv/bin/python（源码树外的 venv）
# venv 需要 PySide6-Essentials 和 pyinstaller。所有中间文件都在源码树的 build/ dist/ 里（已在 .gitignore）。
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PY="${1:-$ROOT/../.venv/bin/python}"
VERSION="${ZGP_VERSION:-0.3.11}"
cd "$ROOT"
"$PY" pet_lines.py
mkdir -p build/ZhangguiPet.iconset
for s in 16 32 128 256 512; do
  sips -z $s $s assets/icon.png --out build/ZhangguiPet.iconset/icon_${s}x${s}.png >/dev/null
  d=$((s * 2)); sips -z $d $d assets/icon.png --out build/ZhangguiPet.iconset/icon_${s}x${s}@2x.png >/dev/null
done
iconutil -c icns build/ZhangguiPet.iconset -o build/ZhangguiPet.icns
export PYINSTALLER_CONFIG_DIR="$ROOT/build/pyi-cache" ZGP_VERSION="$VERSION"
"$PY" -m PyInstaller --noconfirm --clean --workpath build/work --distpath dist packaging/zhanggui_pet_mac.spec
APPD=dist/ZhangguiPet.app
codesign --force --deep --sign - "$APPD"
OUT="dist/ZhangguiPet-v${VERSION}-mac-arm64-test"
rm -rf "$OUT" "$OUT.zip"; mkdir -p "$OUT"
cp -R "$APPD" "$OUT/"
cp README.md LICENSE.txt THIRD_PARTY_NOTICES.txt CHANGELOG.md 说明.txt MAC_PORT.md "$OUT/"
cp -R licenses "$OUT/"
(cd dist && ditto -c -k --keepParent "$(basename "$OUT")" "$(basename "$OUT").zip")
shasum -a 256 "$OUT.zip"
echo "done: $ROOT/$OUT.zip"
