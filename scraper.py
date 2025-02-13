import requests
from bs4 import BeautifulSoup
import urllib3
from requests.adapters import HTTPAdapter
from requests.packages.urllib3.util.retry import Retry
import time
from collections import Counter
import random
from datetime import datetime, timedelta, timezone
import logging
import os

# 設置日誌
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def get_history_from_github():
    """從 GitHub 獲取歷史數據"""
    try:
        repo_name = os.environ.get('REPO_NAME', 'YOUR_USERNAME/YOUR_REPO')
        url = f"https://raw.githubusercontent.com/{repo_name}/main/data/bingo_history.json"
        response = requests.get(url)
        if response.status_code == 200:
            data = response.json()
            return data['records']
    except Exception as e:
        logger.error(f"從 GitHub 獲取數據失敗：{str(e)}")
    return None

def scrape_bingo():
    """抓取開獎數據"""
    # 先嘗試從 GitHub 獲取數據
    github_data = get_history_from_github()
    if github_data:
        logger.info(f"從 GitHub 獲取到 {len(github_data)} 筆數據")
        return github_data
        
    # 如果無法從 GitHub 獲取，則爬取網站
    logger.info("從網站爬取數據...")
    # 關閉 SSL 警告
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
    
    retry_strategy = Retry(
        total=3,
        backoff_factor=1,
        status_forcelist=[500, 502, 503, 504]
    )
    adapter = HTTPAdapter(max_retries=retry_strategy)
    session = requests.Session()
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    
    try:
        print("開始爬取開獎數據...")
        
        # 取得當前時間（台灣時間）並計算日期
        current_time = datetime.now(timezone(timedelta(hours=8)))
        print(f"系統時間：{current_time.strftime('%Y/%m/%d %H:%M')}")
        
        # 如果當前時間小於今天的7:05，表示還在前一天
        today_start = current_time.replace(hour=7, minute=5, second=0, microsecond=0)
        if current_time < today_start:
            current_time = current_time - timedelta(days=1)
            print("還在前一天")
        else:
            print("新的一天")
        
        weekday_map = {
            0: '一',  # 週一
            1: '二',  # 週二
            2: '三',  # 週三
            3: '四',  # 週四
            4: '五',  # 週五
            5: '六',  # 週六
            6: '日'   # 週日
        }
        
        # 檢查並輸出日期時間
        weekday = current_time.weekday()
        print(f"系統星期：{weekday} ({weekday_map[weekday]})")
        print(f"開獎日期：{current_time.strftime('%Y/%m/%d')}({weekday_map[weekday]})")
        
        # 抓取網頁資料
        url = "http://www.pilio.idv.tw/bingo/list.asp?auto=1"
        response = session.get(
            url, 
            headers={
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
            },
            verify=False,
            timeout=30
        )
        
        soup = BeautifulSoup(response.content, 'html.parser')
        tables = soup.find_all('table')
        
        # 尋找開獎資料表格
        main_table = None
        for table in tables:
            if table.find('tr') and 'BINGO BINGO' in table.find('tr').get_text() and '開獎號碼' in table.find('tr').get_text():
                main_table = table
                break
        
        if not main_table:
            print("未找到開獎資料表格")
            return []
        
        # 收集開獎資料
        temp_results = []
        for row in main_table.find_all('tr')[1:]:  # 跳過標題行
            cell = row.find('td')
            if not cell or '【期別:' not in cell.get_text():
                continue
            
            text = cell.get_text(strip=True)
            try:
                # 提取期號
                period = text.split('【期別:')[1].split('】')[0].strip()
                period_num = int(period[-3:])
                
                # 提取開獎號碼
                numbers_text = text.split('】')[1].split('超級獎號:')[0]
                numbers = [int(num.strip()) for num in numbers_text.replace('&nbsp;', '').split(',') 
                          if num.strip().isdigit() and 1 <= int(num.strip()) <= 80]
                
                # 提取超級獎號
                if '超級獎號:' in text:
                    super_text = text.split('超級獎號:')[1].split('_')[0].strip()
                    super_number = int(super_text)
                    if numbers and 1 <= super_number <= 80:
                        temp_results.append((period, period_num, numbers, super_number))
                
            except Exception as e:
                print(f"解析資料時出錯: {e}")
                continue
        
        # 處理時間和排序
        all_results = []
        if temp_results:
            # 按期號排序（從大到小）
            temp_results.sort(key=lambda x: x[1], reverse=True)
            first_period = temp_results[-1][1]  # 取最小期號（最舊的）
            
            for period, period_num, numbers, super_number in temp_results:
                # 計算時間（從7:05開始）
                minutes_diff = (period_num - first_period) * 5
                hours = 7
                minutes = 5 + minutes_diff
                
                # 處理分鐘進位
                if minutes >= 60:
                    hours += minutes // 60
                    minutes = minutes % 60
                
                # 判斷是否為前一天
                is_previous_day = False
                if hours >= 24:
                    is_previous_day = True
                    hours -= 24
                
                # 計算日期
                display_date = current_time - timedelta(days=1) if is_previous_day else current_time
                
                result = {
                    '期號': period,
                    '開獎號碼': numbers,
                    '超級獎號': super_number,
                    '時間': f"{hours:02d}:{minutes:02d}",
                    '是否前一天': is_previous_day,
                    '日期': f"{display_date.strftime('%Y/%m/%d')}({weekday_map[display_date.weekday()]})"
                }
                all_results.append(result)
                print(f"期號 {period} - 開獎號碼: {numbers}, 超級獎號: {super_number}, 時間: {result['時間']}")
        
        if all_results:
            print(f"\n成功獲取 {len(all_results)} 筆開獎資料")
            return all_results
        
        print("未找到開獎資料")
        return []
        
    except Exception as e:
        print(f"發生錯誤: {e}")
        print(f"錯誤類型: {type(e)}")
        import traceback
        print(f"錯誤追蹤:\n{traceback.format_exc()}")
        return []

def get_best_combination(data, periods=10):
    """獲取最佳投注組合"""
    recent_data = data[:periods]
    
    # 統計號碼出現頻率
    number_freq = Counter()
    super_freq = Counter()
    for draw in recent_data:
        number_freq.update(draw['開獎號碼'])
        super_freq.update([draw['超級獎號']])
    
    # 分析超級獎號的歷史模式
    recent_supers = [draw['超級獎號'] for draw in recent_data]
    super_patterns = {
        '連續': [],  # 記錄連續上升或下降的模式
        '區間': [],  # 記錄號碼落在的區間
        '間隔': []   # 記錄相鄰號碼的間隔
    }
    
    # 分析連續性
    for i in range(len(recent_supers)-1):
        diff = recent_supers[i] - recent_supers[i+1]
        super_patterns['連續'].append(diff)
        super_patterns['間隔'].append(abs(diff))
    
    # 分析區間分布
    for super_num in recent_supers:
        if super_num <= 20:
            super_patterns['區間'].append('小')
        elif super_num <= 40:
            super_patterns['區間'].append('中')
        elif super_num <= 60:
            super_patterns['區間'].append('大')
        else:
            super_patterns['區間'].append('特大')
    
    # 生成推薦組合
    recommendations = []
    for _ in range(5):
        # 選擇熱門號碼
        hot_numbers = [num for num, _ in number_freq.most_common(10)]
        numbers = sorted(random.sample(hot_numbers, 3))
        
        # 選擇超級獎號
        super_candidates = [num for num, _ in super_freq.most_common(5)]
        super_number = random.choice(super_candidates)
        
        recommendations.append((numbers, super_number))
    
    return recommendations

def scrape_bingo_history(days=7):
    """抓取指定天數的歷史開獎數據"""
    # 關閉 SSL 警告
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
    
    retry_strategy = Retry(
        total=3,
        backoff_factor=1,
        status_forcelist=[500, 502, 503, 504]
    )
    adapter = HTTPAdapter(max_retries=retry_strategy)
    session = requests.Session()
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    
    try:
        print(f"開始爬取 {days} 天的歷史開獎數據...")
        all_results = []
        page = 0
        
        while True:
            url = f"http://www.pilio.idv.tw/bingo/history.asp?page={page}"
            
            response = session.get(
                url, 
                headers={
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
                    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                    'Accept-Language': 'zh-TW,zh;q=0.9,en-US;q=0.8,en;q=0.7'
                },
                verify=False,
                timeout=30
            )
            
            # 處理編碼
            content_bytes = response.content
            try:
                content = content_bytes.decode('big5')
            except:
                try:
                    content = content_bytes.decode('cp950')
                except:
                    content = content_bytes.decode('utf-8', errors='replace')
            
            if not content:
                print(f"無法獲取第 {page} 頁內容")
                break
            
            soup = BeautifulSoup(content, 'html.parser')
            
            # 找到所有表格
            tables = soup.find_all('table')
            print(f"第 {page} 頁找到 {len(tables)} 個表格")
            
            found_data = False
            
            # 遍歷所有表格尋找開獎資料
            for table in tables:
                rows = table.find_all('tr')
                
                for row in rows:
                    try:
                        cells = row.find_all('td')
                        if len(cells) >= 3:  # 確保有足夠的單元格
                            date_cell = cells[0].get_text(strip=True)
                            period_cell = cells[1].get_text(strip=True)
                            numbers_cell = cells[2].get_text(strip=True)
                            
                            if period_cell and numbers_cell:
                                # 提取期號
                                period = period_cell.strip()
                                print(f"找到期號: {period}")
                                
                                # 提取開獎號碼
                                numbers = []
                                number_texts = numbers_cell.replace('&nbsp;', ' ').replace(',', ' ').split()
                                for num_text in number_texts:
                                    try:
                                        num = int(num_text)
                                        if 1 <= num <= 80:
                                            numbers.append(num)
                                    except:
                                        continue
                                
                                if len(numbers) >= 4:  # 至少要有3個號碼和1個超級獎號
                                    result = {
                                        '日期': date_cell,
                                        '期號': period,
                                        '開獎號碼': numbers[:-1][:3],  # 取前3個號碼
                                        '超級獎號': numbers[-1]  # 最後一個號碼為超級獎號
                                    }
                                    all_results.append(result)
                                    found_data = True
                                    print(f"成功解析：{result}")
                            
                    except Exception as e:
                        print(f"解析資料時出錯：{e}")
                        continue
            
            # 如果這一頁沒有找到任何資料，就停止爬取
            if not found_data:
                print(f"第 {page} 頁未找到資料，停止爬取")
                break
            
            print(f"目前已獲取 {len(all_results)} 筆資料")
            page += 1
            time.sleep(1)  # 避免請求過快
        
        print(f"總共獲取 {len(all_results)} 期開獎資料")
        return sorted(all_results, key=lambda x: int(x['期號']), reverse=True)
        
    except Exception as e:
        print(f"爬取歷史數據時發生錯誤: {e}")
        return all_results if all_results else []

def check_win(bet_numbers, draw_numbers, super_number=None):
    """檢查是否中獎"""
    matches = len(set(bet_numbers) & set(draw_numbers))
    is_super = super_number in bet_numbers if super_number else False
    return matches, is_super

def analyze_results(data, bet_numbers):
    """分析號碼統計"""
    print("\n=== 號碼統計分析 ===")
    print(f"分析號碼: {', '.join(map(str, bet_numbers))}")
    print("=" * 50)
    
    # 初始化統計數據
    total_matches = 0
    super_matches = 0
    match_counts = {0: 0, 1: 0, 2: 0, 3: 0}
    periods_analyzed = 0
    
    # 分析每一期的匹配情況
    for result in data:
        periods_analyzed += 1
        # 計算一般號碼匹配數
        matches = len(set(bet_numbers) & set(result['開獎號碼']))
        match_counts[matches] = match_counts.get(matches, 0) + 1
        total_matches += matches
        
        # 檢查超級獎號匹配
        if result['超級獎號'] in bet_numbers:
            super_matches += 1
            print(f"\n期號 {result['期號']} 中超級獎號！")
            print(f"開獎號碼: {', '.join(map(str, result['開獎號碼']))}")
            print(f"超級獎號: {result['超級獎號']}")
    
    # 計算統計數據
    avg_matches = total_matches / periods_analyzed if periods_analyzed > 0 else 0
    
    # 輸出統計結果
    print("\n統計結果:")
    print("-" * 50)
    print(f"分析期數: {periods_analyzed} 期")
    print(f"平均匹配數: {avg_matches:.2f}")
    print(f"超級獎號匹配次數: {super_matches}")
    
    print("\n匹配分布:")
    for matches, count in sorted(match_counts.items()):
        percentage = (count / periods_analyzed * 100) if periods_analyzed > 0 else 0
        print(f"匹配 {matches} 個號碼: {count} 次 ({percentage:.2f}%)")
    
    # 輸出中獎次數
    win_count = match_counts.get(3, 0) + super_matches
    if win_count > 0:
        print(f"\n總計中獎 {win_count} 次")
        print(f"中獎率: {(win_count / periods_analyzed * 100):.2f}%")
    else:
        print("\n尚未中獎")

def query_winning(data):
    """互動式中獎查詢"""
    print("\n=== 賓果賓果中獎查詢 ===")
    
    # 期號區間查詢
    print("請輸入要查詢的期號區間（格式: 起始期號-結束期號，直接按Enter查詢所有期數）")
    print("範例: 114008437-114008446")
    while True:
        try:
            period_range = input("期號區間: ").strip()
            if not period_range:  # 如果沒有輸入，使用所有期數
                start_period = min(int(result['期號']) for result in data)
                end_period = max(int(result['期號']) for result in data)
            else:
                # 解析期號區間
                if '-' not in period_range:
                    print("請使用'-'分隔起始和結束期號！")
                    continue
                    
                start_period, end_period = map(int, period_range.split('-'))
                
            if start_period > end_period:
                print("起始期號不能大於結束期號！")
                continue
                
            break
        except ValueError:
            print("請輸入有效的期號！格式: 114008437-114008446")
    
    # 號碼查詢
    print("\n請輸入您要查詢的號碼（3個數字，用空格分隔）:")
    while True:
        try:
            numbers_input = input("投注號碼: ")
            bet_numbers = [int(x) for x in numbers_input.split()]
            
            if len(bet_numbers) != 3:
                print("請輸入3個號碼！")
                continue
                
            if not all(1 <= x <= 80 for x in bet_numbers):
                print("號碼必須在1-80之間！")
                continue
                
            break
        except ValueError:
            print("請輸入有效的數字！")
    
    print("\n查詢結果:")
    print("=" * 50)
    
    win_count = 0
    filtered_data = [r for r in data if start_period <= int(r['期號']) <= end_period]
    
    if not filtered_data:
        print(f"找不到期號在 {start_period} 到 {end_period} 之間的資料")
        return
        
    for result in filtered_data:
        matches = len(set(bet_numbers) & set(result['開獎號碼']))
        is_super = result['超級獎號'] in bet_numbers
        
        # 只顯示中獎的結果
        if matches >= 3 or is_super:
            win_count += 1
            print(f"期號: {result['期號']}")
            print(f"開獎號碼: {', '.join(map(str, result['開獎號碼']))}")
            print(f"超級獎號: {result['超級獎號']}")
            print(f"匹配數字: {matches} 個")
            print(f"超級獎號: {'中' if is_super else '沒中'}")
            print("恭喜中獎！")
            print("-" * 50)
    
    if win_count == 0:
        print(f"在期號 {start_period} 到 {end_period} 之間沒有中獎紀錄。")
    else:
        print(f"在期號 {start_period} 到 {end_period} 之間共中獎 {win_count} 次。")

if __name__ == '__main__':
    print("開始爬取數據...")
    data = scrape_bingo()
    if data:
        print("\n最新10期開獎結果:")
        print("=" * 50)
        for result in data[:10]:
            print(f"期號: {result['期號']}")
            print(f"開獎號碼: {', '.join(map(str, result['開獎號碼']))}")
            print(f"超級獎號: {result['超級獎號']}")
            print("-" * 50)
            
        # 詢問是否要查詢中獎
        while True:
            choice = input("\n是否要查詢中獎？(y/n): ").lower()
            if choice == 'y':
                query_winning(data)
            elif choice == 'n':
                break
            else:
                print("請輸入 y 或 n")
    else:
        print("\n未能獲取數據") 