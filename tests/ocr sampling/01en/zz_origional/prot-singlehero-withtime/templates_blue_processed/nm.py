import os
import re
from collections import defaultdict

TAG_MAP = {
    "05": "c0",
    "15": "c1",
    "25": "c2",
    "35": "c3",
    "45": "c4",
}

# 原始文件匹配（带可选颜色）
SRC_PATTERN = re.compile(
    r"""
    ^.*?
    -(05|15|25|35|45)      # 标记串
    (?:-([a-zA-Z]+))?      # 可选颜色（纯字母）
    .*?
    (\.[^.]+)$             # 扩展名
    """,
    re.VERBOSE
)

# 已生成文件匹配：cX_vNN[_color].ext
DST_PATTERN = re.compile(
    r"""
    ^(c[0-4])_v(\d{2})     # cX_vNN
    (?:_[^\.]+)?           # 可选颜色
    \.[^.]+$
    """,
    re.VERBOSE
)

# 1️⃣ 扫描已有文件，找出每个 cX 当前最大序号
max_index = defaultdict(int)

for fname in os.listdir("."):
    m = DST_PATTERN.match(fname)
    if m:
        tag, idx = m.groups()
        max_index[tag] = max(max_index[tag], int(idx))

# 2️⃣ 重命名新文件（续号）
for filename in sorted(os.listdir(".")):
    if not os.path.isfile(filename):
        continue

    match = SRC_PATTERN.match(filename)
    if not match:
        continue

    tag, color, ext = match.groups()
    new_tag = TAG_MAP[tag]

    # 递增序号
    max_index[new_tag] += 1
    index = f"{max_index[new_tag]:02d}"

    if color:
        new_name = f"{new_tag}_v{index}_{color}{ext}"
    else:
        new_name = f"{new_tag}_v{index}{ext}"

    if filename == new_name:
        continue

    print(f"{filename}  ->  {new_name}")
    os.rename(filename, new_name)
