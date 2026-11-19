#!/bin/sh
set -eu
scripts=$(CDPATH='' cd -- "$(dirname -- "$0")" && pwd)
case "$(uname -s)-$(uname -m)" in
  Linux-x86_64) platform=linux-x64 ;;
  Darwin-arm64) platform=macos-arm64 ;;
  *) echo "当前系统暂未提供预构建运行器" >&2; exit 1 ;;
esac
read -r asset expected url <<EOF
$(awk -v key="$platform" '$1==key {print $2, $3, $4}' "$scripts/python-lock.txt")
EOF
cache="${GOODWEN_LOCAL_CACHE:-${XDG_CACHE_HOME:-$HOME/.cache}/goodwen-local}/$platform/$expected"
mkdir -p "$cache"
if [ ! -x "$cache/python/bin/python3" ]; then
  staging=$(mktemp -d "$cache/build.XXXXXXXX")
  trap 'rm -rf "$staging"' EXIT HUP INT TERM
  archive="$scripts/../offline/$asset"
  if [ ! -f "$archive" ]; then
    archive="$staging/python.tar.gz"
    curl --fail --location --silent --show-error --retry 2 --output "$archive" "$url"
  fi
  if command -v sha256sum >/dev/null 2>&1; then actual=$(sha256sum "$archive"); else actual=$(shasum -a 256 "$archive"); fi
  [ "${actual%% *}" = "$expected" ] || { echo "Python 制品摘要不符" >&2; exit 1; }
  tar -xzf "$archive" -C "$staging"
  # 同时安装时只允许一次原子重命名。Python 自身负责处理目标已存在的竞争。
  "$staging/python/bin/python3" -I -c 'import os,sys
try: os.rename(sys.argv[1],sys.argv[2])
except OSError:
 if not os.path.isfile(os.path.join(sys.argv[2],"bin","python3")): raise' "$staging/python" "$cache/python"
  rm -rf "$staging"
  trap - EXIT HUP INT TERM
fi
exec "$cache/python/bin/python3" -I "$scripts/bootstrap.py" "$platform" "$cache" "$@"
