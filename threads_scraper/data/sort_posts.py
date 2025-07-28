import json
import os
from datetime import datetime

def sort_json_by_date(filename):
    with open(filename, 'r', encoding='utf-8') as f:
        posts = json.load(f)

    # 排序貼文，依據 'datetime' 字段
    posts.sort(key=lambda x: datetime.fromisoformat(x['datetime']), reverse=True)

    # 將排序後的結果寫回檔案
    with open(filename, 'w', encoding='utf-8') as f:
        json.dump(posts, f, ensure_ascii=False, indent=4)

    print(f"{filename} 已成功按時間排序")

def sort_all_json_files_in_folder(folder_path):
    for filename in os.listdir(folder_path):
        if filename.endswith(".json"):
            file_path = os.path.join(folder_path, filename)
            sort_json_by_date(file_path)

# 使用範例
if __name__ == "__main__":
    data_folder = "data"  # 指定資料夾路徑
    sort_all_json_files_in_folder(data_folder)