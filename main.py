import os
import logging
import requests 
import json 
import random 
import string 
import asyncio
import re
from urllib.parse import urlparse, urlunparse 
from telegram import Update 
from telegram.ext import Application, MessageHandler, filters
from fastapi import FastAPI, Request 
import uvicorn 

# --- 1. 日志配置 ---
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', 
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# --- 2. 辅助函数：生成随机二级域名 ---
def generate_random_subdomain(min_len=3, max_len=8):
    """生成 3 到 8 位的随机字母和数字组合"""
    length = random.randint(min_len, max_len)
    characters = string.ascii_lowercase + string.digits
    return ''.join(random.choice(characters) for i in range(length))

# -------------------------------------------------------------
# ⭐️ 核心功能函数 (API 获取 A + 静态解析 B + 随机化)
# -------------------------------------------------------------
async def get_final_url(update: Update, context) -> None:
    # 直接使用单机器人的 API_URL
    API_URL = context.application.bot_data.get('API_URL')
    
    if not API_URL:
        await update.message.reply_text("❌ 机器人配置错误，未找到 API URL。")
        logger.error("API_URL not found in application.bot_data.")
        return
        
    # 立即发送回复，这是防止 Telegram 超时的关键
    await update.message.reply_text("正在为您获取最新下载链接，请稍候...")
    
    HEADERS = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36',
        'Accept': 'application/json, text/plain, */*',
    }
    
    domain_a = None
    final_url_b = None
    
    try:
        # ----------------------------------------------
        # 第一步: Requests 请求 API 获取 A 域名
        # ----------------------------------------------
        api_response = requests.get(API_URL, headers=HEADERS, timeout=5)
        api_response.raise_for_status() 
        
        data = api_response.json()
        domain_a = data.get('data') 
        
        if not domain_a or not isinstance(domain_a, str):
            await update.message.reply_text(f"❌ 链接获取失败：API 响应中未找到 A 域名或格式错误。")
            logger.error(f"API response format incorrect. Data retrieved: {domain_a}")
            return

        logger.info(f"Step 2: Successfully retrieved Domain A: {domain_a}. Starting static parsing.")
        
        # ----------------------------------------------
        # 第二步: 纯 Requests 获取 HTML 并静态解析跳转链接
        # ----------------------------------------------
        # 增加 allow_redirects=False，手动处理跳转，以确保我们看到 JS 跳转代码
        page_response = requests.get(domain_a, headers=HEADERS, timeout=10, allow_redirects=False)
        page_response.raise_for_status()
        html_content = page_response.text
        
        # 1. 尝试查找 JS 跳转 (如 window.location.href = '...' 或 location.replace)
        js_match = re.search(r'location\.(?:href|replace)\s*=\s*["\'](.*?)["\']', html_content)
        if js_match:
            final_url_b = js_match.group(1)
            logger.info(f"Found JS redirect: {final_url_b}")
        
        # 2. 尝试查找 Meta Refresh 跳转 (<meta http-equiv="refresh" content="0; url=...">)
        if not final_url_b:
            meta_match = re.search(r'<meta[^>]*http-equiv=["\']refresh["\'][^>]*content=["\'][^;]*;\s*url=(.*?)["\']', html_content, re.IGNORECASE)
            if meta_match:
                final_url_b = meta_match.group(1).strip()
                logger.info(f"Found Meta Refresh redirect: {final_url_b}")

        # 3. 新增：尝试查找 HTML 中的下载链接 (找第一个包含 http/https 的 href 链接，通常是下载链接)
        if not final_url_b:
            # 匹配 <a href="http/https://..."> 标签，或者 <iframe src="http/https://...">
            link_match = re.search(r'(?:href|src)\s*=\s*["\'](http[s]?://[^"\']+)["\']', html_content, re.IGNORECASE)
            if link_match:
                final_url_b = link_match.group(1)
                logger.info(f"Found standard HTML link/src: {final_url_b}")

        # 4. 如果仍未找到，使用原始 URL 作为备选
        if not final_url_b:
            final_url_b = domain_a
            logger.info("No static redirect or standard link found. Using Domain A as final URL.")
        
        
        # ----------------------------------------------
        # 第三步: 随机化二级域名 (与之前逻辑相同)
        # ----------------------------------------------
        
        # 确保 final_url_b 是绝对 URL
        if not final_url_b.startswith("http"):
             # 使用 domain_a 的协议和网络位置来构造一个完整的 URL
            base_url = urlparse(domain_a)
            final_url_b = urlunparse(base_url._replace(path=urlparse(final_url_b).path, query=urlparse(final_url_b).query))


        
        if final_url_b and final_url_b != domain_a: # 只有找到 B 链接才执行随机化，否则跳过
            parsed_url = urlparse(final_url_b)
            netloc_parts = parsed_url.netloc.split('.')
            
            if len(netloc_parts) >= 2: 
                new_subdomain = generate_random_subdomain(3, 8)
                netloc_parts[0] = new_subdomain 
                new_netloc = '.'.join(netloc_parts)
                modified_url_b = urlunparse(parsed_url._replace(netloc=new_netloc))

                await update.message.reply_text(f"✅ 本次最新下载链接是：\n{modified_url_b}")
                logger.info(f"Success! Final URL B (modified): {modified_url_b}")
            else:
                await update.message.reply_text(f"✅ 本次最新下载链接是：\n{final_url_b}")
                logger.warning(f"URL structure not suitable for subdomain replacement. Returning original URL.")
        elif final_url_b == domain_a:
            # 如果解析失败，返回原始 A 域名，并加上一个警告信息
            await update.message.reply_text(f"⚠️ 未能检测到有效跳转，返回原始链接（已随机化）:\n{domain_a}")
            logger.warning(f"Static parsing failed to find redirect. Final URL: {domain_a}")
        else:
             await update.message.reply_text(f"⚠️ 发生了未知解析错误，返回原始链接：\n{domain_a}")
             logger.warning(f"Unexpected parsing state. Final URL: {domain_a}")


    except requests.exceptions.RequestException as req_err:
        await update.message.reply_text(f"❌ 网络请求或 API 失败，请检查 API 接口。")
        logger.error(f"Request Error: {req_err}")
    except Exception as e:
        await update.message.reply_text(f"❌ 发生了意外错误。请联系管理员。")
        logger.error(f"Unexpected Runtime Error: {e}")


# -------------------------------------------------------------
# ⭐️ 单 Bot 配置和初始化
# -------------------------------------------------------------

BOT_TOKEN = os.environ.get("BOT_1_TOKEN") # 仅使用 BOT_1 的 TOKEN
API_URL = os.environ.get("BOT_1_API")     # 仅使用 BOT_1 的 API
WEBHOOK_PATH = "webhook"                  # 简化的 webhook 路径

# 单机器人实例
application = None

async def initialize_single_bot(): 
    """初始化并启动单个 Bot"""
    global application

    if BOT_TOKEN and API_URL:
        application = Application.builder().token(BOT_TOKEN).build()
        application.bot_data['API_URL'] = API_URL
        
        COMMAND_PATTERN = r"^(地址|最新地址|安卓地址|苹果地址|安卓下载地址|苹果下载地址|链接|最新链接|安卓链接|安卓下载链接|最新安卓链接|苹果链接|苹果下载链接|ios链接|最新苹果链接|/start_check)$"
        application.add_handler(
            MessageHandler(
                filters.TEXT & filters.Regex(COMMAND_PATTERN), 
                get_final_url
            )
        )

        await application.initialize() 
        asyncio.create_task(application.start()) 
        logger.info(f"Initialized single bot on path /{WEBHOOK_PATH}")
    else:
        logger.error(f"BOT_1_TOKEN or BOT_1_API not set. Cannot run single bot.")

app = FastAPI()

@app.get("/")
async def root():
    """Render Health Check endpoint."""
    if application:
        return {"status": "ok", "message": f"Bot service running on /{WEBHOOK_PATH}"}
    else:
        return {"status": "error", "message": "Bot not initialized due to missing env vars"}


@app.on_event("startup")
async def startup_event():
    await initialize_single_bot()

@app.post(f"/{WEBHOOK_PATH}")
async def telegram_webhook(request: Request):
    if not application:
        logger.error("Application not initialized.")
        return {"status": "error", "message": "Application not initialized"}

    try:
        data = await request.json()
        update = Update.de_json(data, application.bot)
        await application.update_queue.put(update)
        return {"status": "ok"}
    except Exception as e:
        logger.error(f"Error processing update: {e}")
        return {"status": "error", "message": str(e)} 

if __name__ == "__main__":
    PORT = int(os.environ.get("PORT", 8080))
    # 注意：如果您的 Render Build Command 使用了 'main:app'，您需要将此文件命名为 main.py 
    # 或者将 Render Start Command 更改为 'uvicorn single_bot_app:app --host 0.0.0.0 --port $PORT'
    uvicorn.run(app, host="0.0.0.0", port=PORT)
