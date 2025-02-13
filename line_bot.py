from flask import Flask, request, abort, jsonify
from linebot.v3 import (
    WebhookHandler
)
from linebot.v3.messaging import (
    Configuration,
    ApiClient,
    MessagingApi,
    ReplyMessageRequest,
    TextMessage
)
from linebot.v3.exceptions import InvalidSignatureError
from linebot.v3.webhooks import MessageEvent, TextMessageContent
from datetime import datetime, timedelta
import random
from collections import Counter
import threading
from functools import wraps
import time
import os
import logging

logging.basicConfig(level=logging.INFO)

app = Flask(__name__)

# 從環境變數獲取認證信息
LINE_CHANNEL_ACCESS_TOKEN = os.getenv('LINE_CHANNEL_ACCESS_TOKEN', 'k0LFxb148FVTooSV8cAWaXWovnQ1DPgM8T44BOjGdft1R8mWEfSaR2yqFCs8O5bOg0Q2FcC1YLulLYhBR0ItXXS7vaAOjy+RxD3P6uC3W+ACQqjYhHMJnnH2LFeqx95PbgFWC4FRRv+2pZ7aZA2AjAdB04t89/1O/w1cDnyilFU=')
LINE_CHANNEL_SECRET = os.getenv('LINE_CHANNEL_SECRET', 'd287b4093d6679fc40b0ab8d01e5cda7')

# 初始化 LINE Bot API
configuration = Configuration(access_token=LINE_CHANNEL_ACCESS_TOKEN)
handler = WebhookHandler(LINE_CHANNEL_SECRET)

# 驗證令牌是否有效
try:
    with ApiClient(configuration) as api_client:
        api_instance = MessagingApi(api_client)
        profile = api_instance.get_bot_info()
        app.logger.info(f"LINE Bot 認證成功：{profile.display_name}")
        app.logger.info(f"使用的 token: {LINE_CHANNEL_ACCESS_TOKEN[:10]}...")
        app.logger.info(f"使用的 secret: {LINE_CHANNEL_SECRET}")
        app.logger.info(f"Bot 資訊: {profile}")
except Exception as e:
    app.logger.error(f"LINE Bot 認證失敗：{str(e)}")
    app.logger.error(f"使用的 token: {LINE_CHANNEL_ACCESS_TOKEN[:10]}...")
    app.logger.error(f"使用的 secret: {LINE_CHANNEL_SECRET}")

# 導入原本的賓果分析功能
from scraper import scrape_bingo, get_best_combination, scrape_bingo_history

# 添加超時裝飾器
def timeout(seconds):
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            result = [None]
            def worker():
                try:
                    result[0] = func(*args, **kwargs)
                except Exception as e:
                    print(f"Error in worker: {e}")
                    result[0] = None
            
            thread = threading.Thread(target=worker)
            thread.daemon = True
            thread.start()
            thread.join(seconds)
            
            if thread.is_alive():
                print("Function call timed out")
                return None
            return result[0]
        return wrapper
    return decorator

@app.route("/webhook", methods=['POST', 'GET'])
def webhook():
    if request.method == 'GET':
        app.logger.info("收到 GET 請求")
        return 'OK'
    
    app.logger.info("收到 POST 請求")
    app.logger.info(f"Headers: {dict(request.headers)}")
    
    # 檢查必要的 header
    if 'X-Line-Signature' not in request.headers:
        app.logger.error("缺少 X-Line-Signature")
        return 'Missing signature', 400
        
    signature = request.headers['X-Line-Signature']
    body = request.get_data(as_text=True)
    app.logger.info(f"Request body: {body}")
    app.logger.info(f"Signature: {signature}")
    
    try:
        handler.handle(body, signature)
        app.logger.info("webhook 處理成功")
    except InvalidSignatureError:
        app.logger.error("Invalid signature")
        app.logger.error(f"使用的 secret: {LINE_CHANNEL_SECRET}")
        abort(400)
    except Exception as e:
        app.logger.error(f"處理 webhook 時發生錯誤：{str(e)}")
        app.logger.exception(e)
    
    return 'OK'

@app.route("/", methods=['GET'])
def hello():
    return 'Hello, World!'

@app.route("/health", methods=['GET'])
def health_check():
    """健康檢查端點"""
    try:
        # 嘗試獲取最新數據，確認服務正常
        data = scrape_bingo()
        if data:
            return jsonify({
                'status': 'healthy',
                'last_draw': data[0]['期號'] if data else None
            }), 200
        return jsonify({'status': 'degraded'}), 200
    except Exception as e:
        app.logger.error(f"健康檢查失敗：{str(e)}")
        return jsonify({'status': 'unhealthy'}), 500

def send_line_message_with_retry(line_bot_api, reply_token, message, max_retries=3):
    """添加重試機制的訊息發送函數"""
    for attempt in range(max_retries):
        try:
            line_bot_api.reply_message(
                ReplyMessageRequest(
                    reply_token=reply_token,
                    messages=[TextMessage(text=message)]
                )
            )
            app.logger.info("回覆發送成功")
            return True
        except Exception as e:
            app.logger.error(f"第 {attempt + 1} 次發送失敗：{str(e)}")
            if attempt < max_retries - 1:
                time.sleep(1)  # 等待1秒後重試
                continue
            raise e

@timeout(30)  # 設置30秒超時
def get_bingo_data():
    try:
        return scrape_bingo()
    except Exception as e:
        print(f"Error getting bingo data: {e}")
        return None

def send_reply(event, message):
    """發送回覆訊息的輔助函數"""
    app.logger.info(f"準備發送回覆，token: {event.reply_token}")
    app.logger.info(f"消息內容: {message[:100]}...")
    
    try:
        with ApiClient(configuration) as api_client:
            api_instance = MessagingApi(api_client)
            app.logger.info("開始發送回覆...")
            response = api_instance.reply_message(
                ReplyMessageRequest(
                    reply_token=event.reply_token,
                    messages=[TextMessage(text=message)]
                )
            )
            app.logger.info(f"回覆發送成功：{response}")
    except Exception as e:
        app.logger.error(f"發送回覆時發生錯誤：{str(e)}")
        app.logger.error(f"回覆 token: {event.reply_token}")
        app.logger.error(f"消息內容: {message[:100]}...")

@handler.add(MessageEvent, message=TextMessageContent)
def handle_message(event):
    text = event.message.text.strip()
    app.logger.info(f"收到訊息：{text}")
    app.logger.info(f"來自用戶：{event.source.user_id}")
    app.logger.info(f"回覆 token：{event.reply_token}")
    
    try:
        if text == "1":
            app.logger.info("處理推薦號碼請求")
            data = scrape_bingo()
            app.logger.info(f"獲取到 {len(data) if data else 0} 筆開獎資料")
            
            if data:
                app.logger.info("開始生成推薦組合")
                
                # 生成5組推薦號碼
                recommended_numbers = []
                all_numbers = list(range(1, 81))
                
                for _ in range(5):
                    try:
                        # 隨機選擇3個號碼
                        numbers = sorted(random.sample(all_numbers, 3))
                        recommended_numbers.append(numbers)
                    except Exception as e:
                        app.logger.error(f"生成號碼時發生錯誤：{str(e)}")
                        continue
                
                app.logger.info(f"生成了 {len(recommended_numbers)} 組推薦號碼")
                
                if recommended_numbers:
                    message = (
                        "🎯 本期推薦組合\n"
                        "==================\n"
                    )
                    
                    for i, numbers in enumerate(recommended_numbers, 1):
                        message += (
                            f"組合 {i}：{', '.join(f'{n:02d}' for n in numbers)}\n"
                            "==================\n"
                        )
                    
                    message += (
                        "\n💡 投注建議：\n"
                        "- 三星玩法\n"
                        "- 單注金額：25元\n"
                        "- 建議投注4倍\n"
                        "- 總投注金額：1000元\n"
                        "\n"
                        "⚠️ 提醒：\n"
                        "- 購買時請說出三星四倍十期\n"
                        "- 理性購買，投注有節\n"
                    )
                else:
                    message = "生成推薦號碼時發生錯誤，請稍後再試"
            else:
                message = "無法獲取開獎數據，請稍後再試"
            
            send_reply(event, message)
            
        elif text == "2":
            app.logger.info("處理查詢開獎記錄請求")
            data = scrape_bingo()
            if data and len(data) > 0:
                recent = data[:10]  # 只顯示最近10期
                message = "📊 最近開獎記錄\n==================\n"
                
                for draw in recent:
                    message += (
                        f"期號：{draw['期號']}\n"
                        f"時間：{draw['時間']}\n"
                        f"號碼：{', '.join(f'{n:02d}' for n in draw['開獎號碼'])}\n"
                        f"超級獎號：{draw['超級獎號']:02d}\n"
                        "==================\n"
                    )
                message += f"\n💡 顯示最近10期開獎記錄"
            else:
                message = "無法獲取開獎記錄，請稍後再試"
            
            send_reply(event, message)
            
        elif text == "3":
            message = (
                "🔍 查詢中獎號碼\n"
                "============================\n"
                "請選擇查詢方式：\n"
                "\n"
                "1. 輸入號碼查詢\n"
                "格式：11 22 33\n"
                "（直接輸入3個號碼，查詢最近10期）\n"
                "\n"
                "2. 輸入期號區間查詢\n"
                "格式：起始-結束 號碼1 號碼2 號碼3\n"
                "例如：114008700-114008800 11 12 13\n"
                "\n"
                "3. 查詢最近30期\n"
                "輸入：最近\n"
                "============================\n"
                "💡 請選擇查詢方式"
            )
            send_reply(event, message)
            
        elif text == "4":
            message = (
                "📚 查看歷史記錄\n"
                "============================\n"
                "請選擇查詢方式：\n"
                "\n"
                "1. 查看今日所有記錄\n"
                "輸入：歷史\n"
                "\n"
                "2. 查看最近10期\n"
                "輸入：歷史 10\n"
                "\n"
                "3. 查看最近20期\n"
                "輸入：歷史 20\n"
                "============================\n"
                "💡 請選擇查詢方式"
            )
            send_reply(event, message)
            
        elif "呼叫" in text or "助手" in text:
            message = (
                "👋 歡迎光臨！我是Corn團隊助手\n"
                "============================\n"
                "🤔 不確定要做什麼？\n"
                "這是我目前的功能：\n"
                "\n"
                "1️⃣ 輸入數字「1」\n"
                "- 獲取本期推薦號碼\n"
                "\n"
                "2️⃣ 輸入數字「2」\n"
                "- 查看最近開獎記錄\n"
                "\n"
                "3️⃣ 輸入數字「3」\n"
                "- 查詢中獎號碼\n"
                "\n"
                "4️⃣ 輸入數字「4」\n"
                "- 查看更多歷史記錄\n"
                "============================\n"
                "💡 請選擇功能編號！"
            )
            send_reply(event, message)
            
        # 處理最近30期查詢
        elif text == "最近":
            app.logger.info("處理最近30期查詢")
            data = scrape_bingo()
            if data:
                recent = data[:30]  # 改為30期
                message = "📊 最近30期開獎記錄\n============================\n"
                
                for draw in recent:
                    message += (
                        f"期號：{draw['期號']}\n"
                        f"時間：{draw['時間']}\n"
                        f"號碼：{', '.join(f'{n:02d}' for n in draw['開獎號碼'])}\n"
                        f"超級獎號：{draw['超級獎號']:02d}\n"
                        "============================\n"
                    )
                message += f"\n💡 顯示最近30期開獎記錄"
            else:
                message = "無法獲取開獎資料，請稍後再試"
            
            send_reply(event, message)
            
        # 處理期號區間查詢（新格式）
        elif "-" in text:
            app.logger.info("處理期號區間查詢")
            try:
                parts = text.split()
                if len(parts) < 4:  # 至少需要：範圍 三個號碼
                    message = "請輸入正確的格式！\n例如：114008700-114008800 11 12 13"
                else:
                    period_range = parts[0].split("-")
                    if len(period_range) != 2:
                        message = "期號範圍格式錯誤！\n例如：114008700-114008800"
                    else:
                        start_period = int(period_range[0])
                        end_period = int(period_range[1])
                        numbers = [int(n) for n in parts[1:4]]
                        
                        if not all(1 <= n <= 80 for n in numbers):
                            message = "號碼必須在1-80之間！"
                        else:
                            data = scrape_bingo()
                            if data:
                                filtered_data = [
                                    draw for draw in data 
                                    if start_period <= int(draw['期號']) <= end_period
                                ]
                                
                                matches = []
                                for draw in filtered_data:
                                    matched = set(numbers) & set(draw['開獎號碼'])
                                    is_super = draw['超級獎號'] in numbers
                                    
                                    # 只顯示匹配2個以上的結果
                                    if len(matched) >= 2 or is_super:
                                        matches.append({
                                            '期號': draw['期號'],
                                            '時間': draw['時間'],
                                            '匹配數字': matched,
                                            '超級獎號': is_super
                                        })
                                
                                if matches:
                                    message = f"🎯 期號 {start_period} 到 {end_period} 查詢結果\n==================\n"
                                    for match in matches:
                                        message += (
                                            f"期號：{match['期號']}\n"
                                            f"時間：{match['時間']}\n"
                                            f"匹配號碼：{', '.join(f'{n:02d}' for n in match['匹配數字'])}\n"
                                            f"超級獎號：{'中' if match['超級獎號'] else '未中'}\n"
                                            "==================\n"
                                        )
                                    message += f"\n💡 共找到 {len(matches)} 筆匹配記錄"
                                else:
                                    message = "❌ 在指定期號範圍內未找到匹配記錄"
                            else:
                                message = "無法獲取開獎資料，請稍後再試"
            except ValueError:
                message = "請輸入有效的期號和號碼！"
            except Exception as e:
                app.logger.error(f"處理期號查詢時發生錯誤：{str(e)}")
                message = "查詢時發生錯誤，請稍後再試"
            
            send_reply(event, message)
            
        # 處理純數字查詢（最近10期）
        elif text.replace(" ", "").isdigit():
            app.logger.info("處理號碼查詢請求")
            try:
                numbers = [int(n) for n in text.split()]
                if len(numbers) != 3:
                    message = "請輸入3個號碼！"
                elif not all(1 <= n <= 80 for n in numbers):
                    message = "號碼必須在1-80之間！"
                else:
                    data = scrape_bingo()
                    if data:
                        recent_data = data[:10]  # 改為10期
                        matches = []
                        
                        for draw in recent_data:
                            matched = set(numbers) & set(draw['開獎號碼'])
                            is_super = draw['超級獎號'] in numbers
                            
                            # 只顯示匹配2個以上的結果
                            if len(matched) >= 2 or is_super:
                                matches.append({
                                    '期號': draw['期號'],
                                    '時間': draw['時間'],
                                    '匹配數字': matched,
                                    '超級獎號': is_super
                                })
                        
                        if matches:
                            message = "🎯 查詢結果\n============================\n"
                            for match in matches:
                                message += (
                                    f"期號：{match['期號']}\n"
                                    f"時間：{match['時間']}\n"
                                    f"匹配號碼：{', '.join(f'{n:02d}' for n in match['匹配數字'])}\n"
                                    f"超級獎號：{'中' if match['超級獎號'] else '未中'}\n"
                                    "============================\n"
                                )
                            message += f"\n💡 共找到 {len(matches)} 筆匹配記錄"
                        else:
                            message = "❌ 在最近10期中未找到匹配記錄"
                    else:
                        message = "無法獲取開獎資料，請稍後再試"
            except ValueError:
                message = "請輸入有效的數字！"
            
            send_reply(event, message)
            
        # 處理歷史記錄查詢
        elif text == "歷史":
            app.logger.info("處理今日歷史記錄查詢")
            data = scrape_bingo()
            if data:
                # 限制顯示最近20期
                recent = data[:20]
                
                # 取得期號範圍
                start_period = recent[-1]['期號']  # 最早的期號
                end_period = recent[0]['期號']    # 最新的期號
                
                message = (
                    f"📊 今日 {start_period} 至 {end_period}\n"
                    "============================\n"
                )
                
                for draw in recent:
                    # 縮短顯示格式
                    numbers_str = ', '.join(f'{n:02d}' for n in draw['開獎號碼'][:10])
                    if len(draw['開獎號碼']) > 10:
                        numbers_str += "..."
                    
                    message += (
                        f"期號：{draw['期號']}\n"  # 顯示完整期號
                        f"時間：{draw['時間']}\n"
                        f"號碼：{numbers_str}\n"
                        f"超級：{draw['超級獎號']:02d}\n"
                        "----------------------------\n"
                    )
                message += f"\n💡 顯示 {start_period} 至 {end_period}"
            else:
                message = "無法獲取開獎資料，請稍後再試"
            
            send_reply(event, message)
            
        elif text.startswith("歷史 "):
            app.logger.info("處理指定期數查詢")
            try:
                num = int(text.split()[1])
                if num <= 0:
                    message = "請輸入大於0的數字！"
                elif num > 50:
                    message = "最多只能查詢50期！"
                else:
                    data = scrape_bingo()
                    if data:
                        # 限制最多顯示20期
                        num = min(num, 20)
                        recent = data[:num]
                        
                        # 取得期號範圍
                        start_period = recent[-1]['期號']  # 最早的期號
                        end_period = recent[0]['期號']    # 最新的期號
                        
                        message = (
                            f"📊 期號 {start_period} 至 {end_period}\n"
                            "============================\n"
                        )
                        
                        for draw in recent:
                            # 縮短顯示格式
                            numbers_str = ', '.join(f'{n:02d}' for n in draw['開獎號碼'][:10])
                            if len(draw['開獎號碼']) > 10:
                                numbers_str += "..."
                            
                            message += (
                                f"期號：{draw['期號']}\n"  # 顯示完整期號
                                f"時間：{draw['時間']}\n"
                                f"號碼：{numbers_str}\n"
                                f"超級：{draw['超級獎號']:02d}\n"
                                "----------------------------\n"
                            )
                        message += f"\n💡 顯示 {start_period} 至 {end_period}"
                    else:
                        message = "無法獲取開獎資料，請稍後再試"
            except ValueError:
                message = "請輸入有效的數字！"
            except Exception as e:
                app.logger.error(f"處理歷史記錄查詢時發生錯誤：{str(e)}")
                message = "查詢時發生錯誤，請稍後再試"
            
            send_reply(event, message)
            
    except Exception as e:
        app.logger.error(f"處理訊息時發生錯誤：{str(e)}")
        app.logger.exception(e)
        message = "系統發生錯誤，請稍後再試"
        send_reply(event, message)

if __name__ == "__main__":
    # 如果是在本地運行
    if os.environ.get('RENDER') != 'true':
        app.run(
            host='0.0.0.0',
            port=8000,
            debug=True,
            threaded=True
        )
    else:
        # 在 Render 上運行
        port = int(os.environ.get('PORT', 10000))
        app.run(
            host='0.0.0.0',
            port=port
        ) 