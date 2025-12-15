import hashlib
import json
import os

def hash_post(post):
    """
    將貼文的所有字段組合成一個字符串或 JSON 結構，並生成哈希值。
    """
    post_str = json.dumps(post, sort_keys=True)
    return hashlib.md5(post_str.encode('utf-8')).hexdigest()

def save_posts_to_file(posts, filename):
    """
    保存貼文數據到指定的JSON文件中。
    """
    os.makedirs(os.path.dirname(filename), exist_ok=True)
    with open(filename, 'w', encoding='utf-8') as f:
        json.dump(posts, f, ensure_ascii=False, indent=4)

def load_existing_posts(filename):
    """
    從指定的文件中加載現有的貼文數據。
    """
    if os.path.exists(filename):
        with open(filename, 'r', encoding='utf-8') as f:
            return json.load(f)
    return []

def remove_duplicates(posts):
    """
    去除貼文數據中的重複項，根據哈希值判斷是否不同。
    """
    seen = {}
    for post in posts:
        key = post['post_link']
        post_hash = hash_post(post)
        if key in seen:
            if seen[key]['hash'] != post_hash:
                seen[key] = {'hash': post_hash, 'post': post}
        else:
            seen[key] = {'hash': post_hash, 'post': post}
    return [entry['post'] for entry in seen.values()]