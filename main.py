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
        # 匹配 location.href = 'URL' 或 location.replace('URL')
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

        # 3. 如果没找到静态跳转，使用原始 URL 作为备选
        if not final_url_b:
            final_url_b = domain_a
            logger.info("No static redirect found. Using Domain A as final URL.")
        
        
        # ----------------------------------------------
        # 第三步: 随机化二级域名 (与之前逻辑相同)
        # ----------------------------------------------
        
        # 确保 final_url_b 是绝对 URL
        if not final_url_b.startswith("http"):
             # 使用 domain_a 的协议和网络位置来构造一个完整的 URL
            base_url = urlparse(domain_a)
            final_url_b = urlunparse(base_url._replace(path=final_url_b))

        
        if final_url_b:
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
        else:
            await update.message.reply_text(f"⚠️ 未能检测到有效跳转，返回原始链接：\n{domain_a}")
            logger.warning(f"Static parsing failed to find redirect. Final URL: {domain_a}")


    except requests.exceptions.RequestException as req_err:
        await update.message.reply_text(f"❌ 网络请求或 API 失败，请检查 API 接口。")
        logger.error(f"Request Error: {req_err}")
    except Exception as e:
        await update.message.reply_text(f"❌ 发生了意外错误。请联系管理员。")
        logger.error(f"Unexpected Runtime Error: {e}")


# -------------------------------------------------------------
# ⭐️ Bot 配置和初始化 (保持不变)
# -------------------------------------------------------------
# 机器人配置列表 (使用环境变量)
BOT_CONFIGS = [
    {
        "token": os.environ.get("BOT_1_TOKEN"),
        "api_url": os.environ.get("BOT_1_API"),
        "path": "bot1_webhook"
    },
    {
        "token": os.environ.get("BOT_4_TOKEN"),
        "api_url": os.environ.get("BOT_4_API"),
        "path": "bot4_webhook"
    },
    {
        "token": os.environ.get("BOT_6_TOKEN"),
        "api_url": os.environ.get("BOT_6_API"),
        "path": "bot6_webhook"
    },
    {
        "token": os.environ.get("BOT_9_TOKEN"),
        "api_url": os.environ.get("BOT_9_API"),
        "path": "bot9_webhook"
    }
]

APPLICATIONS = {}

async def initialize_bots(): 
    """初始化并启动所有 Bot 的后台线程"""
    for config in BOT_CONFIGS:
        token = config['token']
        api_url = config['api_url'] 
        path = config['path']

        if token and api_url:
            application = Application.builder().token(token).build()
            application.bot_data['API_URL'] = api_url
            
            COMMAND_PATTERN = r"^(地址|最新地址|安卓地址|苹果地址|安卓下载地址|苹果下载地址|链接|最新链接|安卓链接|安卓下载链接|最新安卓链接|苹果链接|苹果下载链接|ios链接|最新苹果链接|/start_check)$"
            application.add_handler(
                MessageHandler(
                    filters.TEXT & filters.Regex(COMMAND_PATTERN), 
                    get_final_url
                )
            )

            await application.initialize() 
            asyncio.create_task(application.start()) 
            
            APPLICATIONS[path] = application
            logger.info(f"Initialized bot on path /{path}")
        else:
            logger.warning(f"Skipping bot with path /{path}: TOKEN or API_URL not set.")

app = FastAPI()

@app.get("/")
async def root():
    """Render Health Check endpoint."""
    return {"status": "ok", "message": "Bot service is running"}

@app.on_event("startup")
async def startup_event():
    await initialize_bots()

@app.post("/{path_suffix}")
async def telegram_webhook(path_suffix: str, request: Request):
    application = APPLICATIONS.get(path_suffix)
    if not application:
        logger.warning(f"Webhook received for unknown path: /{path_suffix}")
        return {"status": "error", "message": "Unknown path"}

    try:
        data = await request.json()
        update = Update.de_json(data, application.bot)
        await application.update_queue.put(update)
        return {"status": "ok"}
    except Exception as e:
        logger.error(f"Error processing update for /{path_suffix}: {e}")
        return {"status": "error", "message": str(e)} 

if __name__ == "__main__":
    PORT = int(os.environ.get("PORT", 8080))
    uvicorn.run(app, host="0.0.0.0", port=PORT)
