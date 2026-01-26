import cv2
import numpy as np
import os
import shutil
from sklearn.cluster import KMeans

# ========= 配置 =========
INPUT_DIR = "output_slices"
OUTPUT_DIR = "clusters"
CLUSTER_COUNT = 10      # 你可以先随便给一个
IMG_SIZE = 64           # 统一尺寸，利于比较
# ========================

os.makedirs(OUTPUT_DIR, exist_ok=True)

features = []
files = []

def extract_hu_moments(img):
    moments = cv2.moments(img)
    hu = cv2.HuMoments(moments).flatten()

    # log 变换（标准做法）
    for i in range(len(hu)):
        hu[i] = -np.sign(hu[i]) * np.log10(abs(hu[i]) + 1e-10)

    return hu

# 1️⃣ 提取特征
for file in os.listdir(INPUT_DIR):
    if not file.lower().endswith(".png"):
        continue

    path = os.path.join(INPUT_DIR, file)
    img = cv2.imread(path, cv2.IMREAD_GRAYSCALE)

    # 二值化 & 统一尺寸
    _, img = cv2.threshold(img, 127, 255, cv2.THRESH_BINARY)
    img = cv2.resize(img, (IMG_SIZE, IMG_SIZE), interpolation=cv2.INTER_NEAREST)

    hu = extract_hu_moments(img)

    features.append(hu)
    files.append(file)

features = np.array(features)

# 2️⃣ 聚类
kmeans = KMeans(n_clusters=CLUSTER_COUNT, random_state=0)
labels = kmeans.fit_predict(features)

# 3️⃣ 按聚类结果建文件夹
for file, label in zip(files, labels):
    cluster_dir = os.path.join(OUTPUT_DIR, f"cluster_{label:02d}")
    os.makedirs(cluster_dir, exist_ok=True)

    src = os.path.join(INPUT_DIR, file)
    dst = os.path.join(cluster_dir, file)

    shutil.copy(src, dst)

print("完成：相似图形已归类")
