import os
import logging
import requests 
import json 
import random # <-- 新增导入
import string # <-- 新增导入
from urllib.parse import urlparse, urlunparse # <-- 新增导入
from telegram import Update 
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters
from playwright.async_api import async_playwright

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
    # 仅使用小写字母和数字
    characters = string.ascii_lowercase + string.digits
    return ''.join(random.choice(characters) for i in range(length))

# --- 3. 核心功能函数 (API 获取 A + Playwright 追踪 B) ---
async def get_final_url(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    # ⭐️ 步骤一：不变的 API 接口 (获取会变的 A 域名)
    API_URL = "https://ndbjz.dbgck.com/mapi/alink/zdm3nwuyym"
    
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
        logger.info(f"Step 1: Requesting API URL: {API_URL}")
        api_response = requests.get(API_URL, headers=HEADERS, timeout=5)
        api_response.raise_for_status() 
        
        # --- 准确的 API 解析逻辑 (根据确认的 JSON 结构) ---
        data = api_response.json()
        domain_a = data.get('data') # A 域名直接位于顶级键 "data" 之下
        
        if not domain_a or not isinstance(domain_a, str):
             await update.message.reply_text(f"❌ 链接获取失败：API 响应中未找到 A 域名或格式错误。")
             logger.error(f"API response format incorrect. Data retrieved: {domain_a}")
             return

        logger.info(f"Step 2: Successfully retrieved Domain A: {domain_a}")
        
        # ----------------------------------------------
        # 第二步: Playwright 追踪 A 域名到 B 域名
        # ----------------------------------------------
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True, timeout=15000)
            page = await browser.new_page()

            await page.goto(domain_a, wait_until="networkidle", timeout=30000) 

            final_url_b = page.url
            
            await browser.close() 

            if final_url_b and final_url_b != domain_a:
                
                # --- ⭐️ 核心新增逻辑：修改二级域名 (Subdomain) ---
                parsed_url = urlparse(final_url_b)
                netloc_parts = parsed_url.netloc.split('.')
                
                # 确保 URL 至少有三部分 (subdomain.domain.tld)
                if len(netloc_parts) >= 2: 
                    # 1. 生成随机子域名
                    new_subdomain = generate_random_subdomain(3, 8)
                    
                    # 2. 替换旧的二级域名（它是 netloc 的第一部分，索引 0）
                    netloc_parts[0] = new_subdomain
                    
                    # 3. 重构新的 netloc
                    new_netloc = '.'.join(netloc_parts)
                    
                    # 4. 重构完整的 URL
                    modified_url_b = urlunparse(parsed_url._replace(netloc=new_netloc))

                    await update.message.reply_text(f"✅ 本次最新下载链接是：\n{modified_url_b}")
                    logger.info(f"Success! Final URL B (modified): {modified_url_b}")
                else:
                    # 如果 URL 结构不包含二级域名，则返回原 URL
                    await update.message.reply_text(f"✅ 本次最新下载链接是：\n{final_url_b}")
                    logger.warning(f"URL structure not suitable for subdomain replacement. Returning original URL.")
            else:
                await update.message.reply_text(f"⚠️ Playwright 未检测到跳转。可能 A 域名返回静态页。当前URL: {final_url_b}")
                logger.warning(f"Playwright finished, but no redirect detected. Final URL: {final_url_b}")

    except requests.exceptions.RequestException as e:
        await update.message.reply_text(f"❌ API 请求失败，出现网络错误或超时。")
        logger.error(f"API Request Error: {e}")
    except json.JSONDecodeError:
        await update.message.reply_text(f"❌ API 返回的不是有效的 JSON 格式。请检查 API 接口。")
        logger.error(f"JSON Decode Error in API response.")
    except Exception as e:
        await update.message.reply_text(f"❌ 浏览器错误。请等待几分钟或联系管理员。")
        logger.error(f"Playwright Runtime Error: {e}")

# --- 4. Webhook 主函数 (多命令逻辑) ---
def main() -> None:
    TOKEN = os.environ.get("TELEGRAM_TOKEN")
    
    if not TOKEN:
        logger.error("TELEGRAM_TOKEN is not set. Exiting.")
        return

    WEBHOOK_URL = os.environ.get("RENDER_EXTERNAL_URL")
    PORT = int(os.environ.get("PORT", 8080))

    if not WEBHOOK_URL:
        logger.warning("RENDER_EXTERNAL_URL is not yet available. Proceeding...")

    # NameError 修正
    full_webhook_url = f"{WEBHOOK_URL}/telegram" if WEBHOOK_URL else None 
    
    application = Application.builder().token(TOKEN).build()
    
    # ⭐️ 使用 Regex 匹配多个中文命令
    COMMAND_PATTERN = r"^(地址|最新地址|安卓地址|苹果地址|安卓下载地址|苹果下载地址|链接|最新链接|安卓链接|安卓下载链接|最新安卓链接|苹果链接|苹果下载链接|ios链接|最新苹果链接|/start_check)$"
    
    application.add_handler(
        MessageHandler(
            filters.TEXT & filters.Regex(COMMAND_PATTERN), 
            get_final_url
        )
    )
    
    if full_webhook_url:
        logger.info(f"Attempting to set webhook on port {PORT} to: {full_webhook_url}")
        application.run_webhook(
            listen="0.0.0.0",
            port=PORT,
            url_path="/telegram",
            webhook_url=full_webhook_url,
        )
        logger.info(f"Webhook process started.")
    else:
        logger.error("Could not determine full webhook URL. Deployment might be stuck.")

if __name__ == "__main__":
    main()
