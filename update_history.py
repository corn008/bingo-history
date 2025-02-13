import json
from datetime import datetime, timezone, timedelta
from scraper import scrape_bingo
import os
import requests
from github import Github
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def load_existing_data():
    """從 GitHub 加載現有數據"""
    try:
        repo_name = os.environ.get('REPO_NAME', 'YOUR_USERNAME/YOUR_REPO')
        url = f"https://raw.githubusercontent.com/{repo_name}/main/data/bingo_history.json"
        response = requests.get(url)
        if response.status_code == 200:
            return response.json()
    except Exception as e:
        logger.error(f"加載現有數據失敗：{str(e)}")
    return {"last_updated": "", "records": []}

def update_history():
    """更新歷史數據"""
    # 獲取現有數據
    existing_data = load_existing_data()
    existing_records = {record['期號']: record for record in existing_data['records']}
    
    # 爬取新數據
    new_data = scrape_bingo()
    if not new_data:
        logger.error("爬取新數據失敗")
        return False
        
    # 合併數據
    for record in new_data:
        if record['期號'] not in existing_records:
            existing_records[record['期號']] = record
    
    # 按期號排序
    sorted_records = sorted(existing_records.values(), 
                          key=lambda x: x['期號'], 
                          reverse=True)
    
    # 更新數據
    updated_data = {
        "last_updated": datetime.now(timezone(timedelta(hours=8))).isoformat(),
        "records": sorted_records
    }
    
    # 保存到 GitHub
    try:
        g = Github(os.environ['GITHUB_TOKEN'])
        repo_name = os.environ.get('REPO_NAME', 'YOUR_USERNAME/YOUR_REPO')
        repo = g.get_repo(repo_name)
        
        # 獲取現有文件
        try:
            contents = repo.get_contents("data/bingo_history.json")
            sha = contents.sha
        except:
            sha = None
        
        # 更新或創建文件
        repo.update_file(
            "data/bingo_history.json",
            f"Update bingo history {updated_data['last_updated']}",
            json.dumps(updated_data, ensure_ascii=False, indent=2),
            sha
        )
        
        logger.info("成功更新歷史數據")
        return True
        
    except Exception as e:
        logger.error(f"保存到 GitHub 失敗：{str(e)}")
        return False

if __name__ == "__main__":
    update_history() 