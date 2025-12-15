import json
import os
from datetime import datetime, timedelta
from g4f.client import Client

def load_data_from_json(data_folder):
    """
    讀取 data 資料夾中的所有 JSON 文件，排除檔名中包含 "search" 的檔案，並返回數據列表。
    """
    all_data = []
    for filename in os.listdir(data_folder):
        if filename.endswith(".json") and "search" not in filename:
            with open(os.path.join(data_folder, filename), 'r', encoding='utf-8') as file:
                data = json.load(file)
                all_data.extend(data)
    return all_data

def sort_data_by_recency(data, recent_threshold_days=7):
    """
    將數據按照距今時間進行排序，並分為最近的事件和過去的背景資料。
    """
    now = datetime.utcnow()
    recent_threshold = now - timedelta(days=recent_threshold_days)

    recent_data = []
    older_data = []

    for item in data:
        post_time = datetime.strptime(item['datetime'], '%Y-%m-%dT%H:%M:%S.%fZ')
        if post_time > recent_threshold:
            recent_data.append(item)
        else:
            older_data.append(item)
    
    # 按照時間降序排序最近的事件
    recent_data.sort(key=lambda x: datetime.strptime(x['datetime'], '%Y-%m-%dT%H:%M:%S.%fZ'), reverse=True)
    
    return recent_data, older_data

def generate_content_with_g4f(recent_data, older_data, prompt_template):
    """
    使用 g4f 庫來生成 GPT-4o 的內容，基於數據和提示模板。
    """
    client = Client()

    # 將數據嵌入到提示模板中
    recent_summary = "\n".join([f"- {item['content']}" for item in recent_data])
    older_summary = "\n".join([f"- {item['content']}" for item in older_data])
    
    # 創建系統訊息
    system_message = older_summary
    
    # 創建用戶訊息
    user_message = "按照以下資料，以最重大的事件為主題發表評論文章（必須限制在500字內）：\n\n" + recent_summary

    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": system_message},
            {"role": "user", "content": user_message}
        ],
    )

    return response.choices[0].message.content.strip()

def generate_post():
    """
    外部調用的函數，用於生成貼文內容。
    """
    data_folder = "./data"
    prompt_template = (
        "根據以下最近的事件生成一個簡短的社交媒體帖子：\n\n"
        "{recent_summary}\n\n"
        "另外，以下是過去的相關背景資料，可以作為參考：\n\n"
        "{older_summary}\n\n"
        "請基於上述內容生成一個簡短的、有吸引力的帖子。"
    )
    data = load_data_from_json(data_folder)
    recent_data, older_data = sort_data_by_recency(data)
    return generate_content_with_g4f(recent_data, older_data, prompt_template)