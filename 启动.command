#!/bin/bash
# 合同智能识别系统 - v2：直接用浏览器打开，无需 Python / 本地服务器
DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
if command -v open &> /dev/null; then open "$DIR/index.html"
elif command -v xdg-open &> /dev/null; then xdg-open "$DIR/index.html"
else echo "请用浏览器打开：$DIR/index.html"; fi
