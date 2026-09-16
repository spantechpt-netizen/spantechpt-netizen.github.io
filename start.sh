#!/usr/bin/env bash
# ===========================================================
#  Span Tech CRM — تشغيل نسخة التجربة على لينكس / ماك
#    ./start.sh
# ===========================================================
set -e
cd "$(dirname "$0")"

if ! command -v node >/dev/null 2>&1; then
  cat <<'MSG'

  Node.js مش متنصّب على الجهاز ده.

  نزّله من:  https://nodejs.org
  اختار نسخة LTS (لازم تكون 22.5 أو أحدث)، وبعدين شغّل الملف تاني.

MSG
  exit 1
fi

MAJOR=$(node -p "process.versions.node.split('.')[0]")
MINOR=$(node -p "process.versions.node.split('.')[1]")
if [ "$MAJOR" -lt 22 ] || { [ "$MAJOR" -eq 22 ] && [ "$MINOR" -lt 5 ]; }; then
  echo
  echo "  إصدار Node القديم مش كفاية — الموجود عندك: $(node -p 'process.versions.node')"
  echo "  المطلوب: 22.5 أو أحدث.  نزّل من https://nodejs.org"
  echo
  exit 1
fi

npm run demo

# يفتح المتصفح أول ما السيرفر يرد فعلاً — مش بعد وقت محدد
node --no-warnings scripts/open-when-ready.mjs &

echo "  السيرفر شغال. اضغط Ctrl+C عشان توقفه."
echo
npm start
