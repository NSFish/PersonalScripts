find . -name "*.ass" -exec sh -c 'iconv -f UTF-16 -t UTF-8 "{}" > "{}.utf8"' \;
find . -name "*.ass" -print0 | xargs -0 rm
find . -name "*.utf8" -exec rename 's/\.utf8$//' {} +