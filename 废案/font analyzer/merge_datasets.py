import os
import shutil
from pathlib import Path

def merge_datasets(src_dirs, dst_dir, suffixes=None):
    """
    合并多个 dataset_xxx_font 到一个目标目录
    - src_dirs: 源目录列表
    - dst_dir: 目标目录
    - suffixes: 每个源目录对应的后缀（用于重名文件避免冲突）
    """
    dst_dir = Path(dst_dir)
    dst_dir.mkdir(parents=True, exist_ok=True)

    for idx, src in enumerate(src_dirs):
        src = Path(src)
        suffix = suffixes[idx] if suffixes and idx < len(suffixes) else f"_{idx}"

        for subfolder in ["templates", "words"]:
            src_sub = src / subfolder
            dst_sub = dst_dir / subfolder
            if not src_sub.exists():
                continue

            for hdir in src_sub.iterdir():
                if not hdir.is_dir():
                    continue
                dst_hdir = dst_sub / hdir.name
                dst_hdir.mkdir(parents=True, exist_ok=True)

                for f in hdir.glob("*.png"):
                    dst_file = dst_hdir / f.name
                    if dst_file.exists():
                        # 文件名冲突，加后缀
                        stem, ext = f.stem, f.suffix
                        new_name = f"{stem}{suffix}{ext}"
                        dst_file = dst_hdir / new_name
                    shutil.copy2(f, dst_file)

    print(f"✅ 合并完成，输出目录: {dst_dir}")

if __name__ == "__main__":
    # 你两个源目录
    src_dirs = ["Eng_font_dataset", "Chs_font_dataset"]
    # 每个源目录的后缀（避免文件名冲突）
    suffixes = ["_eng", "_chs"]
    # 合并后的目标目录
    dst_dir = "ocr_font_dataset"

    merge_datasets(src_dirs, dst_dir, suffixes)