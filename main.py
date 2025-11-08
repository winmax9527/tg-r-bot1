import os
import logging
import requests
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

# --- 1. 日志配置（修复 NameError） ---
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', 
    level=logging.INFO
)
# 定义 logger 实例供全局使用
logger = logging.getLogger(__name__)

# --- 2. 核心功能函数 ---
async def get_final_url(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    # !!! 请将此处的域名替换为您实际需要追踪的域名 A !!!
    DOMAIN_A = "https://owzmz.ivqrrox.com/37mC45B/mdgxmzlkzt" 
    
    await update.message.reply_text("正在为您获取最终动态链接，请稍候...")
    
    try:
        # 使用 requests 库发起 GET 请求并自动跟踪重定向
        response = requests.get(DOMAIN_A, allow_redirects=True, timeout=10)
        
        # 检查是否成功
        if 200 <= response.status_code < 400:
            # response.url 是最终重定向后的 URL (域名 B)
            final_url_b = response.url
            
            await update.message.reply_text(f"✅ 最终动态域名 B 是：\n{final_url_b}")
        else:
            await update.message.reply_text(f"❌ 链接获取失败，域名 A 返回了状态码: {response.status_code}")
            logger.error(f"Request failed with status code {response.status_code} for {DOMAIN_A}")
            
    except requests.exceptions.RequestException as e:
        await update.message.reply_text(f"❌ 链接获取失败，出现网络错误。")
        logger.error(f"Request Error: {e}")

# --- 3. Webhook 主函数（简化 Token 检查） ---
def main() -> None:
    # 从 Render 环境变量中获取配置
    TOKEN = os.environ.get("TELEGRAM_TOKEN")
    
    # 关键检查：仅检查 TOKEN
    if not TOKEN:
        logger.error("TELEGRAM_TOKEN is not set. Exiting.")
        return

    # Render 会自动设置外部 URL 和端口
    WEBHOOK_URL = os.environ.get("RENDER_EXTERNAL_URL")
    PORT = int(os.environ.get("PORT", 8080))

    if not WEBHOOK_URL:
        # 如果 WEBHOOK_URL 缺失，给一个警告，但继续运行，让 Render 处理后续的 URL 分配
        logger.warning("RENDER_EXTERNAL_URL is not yet available. Proceeding...")

    # 构建完整的 Webhook URL
    full_webhook_url = f"{WEBHOOK_URL}/telegram" if WEBHOOK_URL else None
    
    # 构建 Application
    application = Application.builder().token(TOKEN).build()

    # 注册命令处理器：用户发送 /start_check 时触发
    application.add_handler(CommandHandler("start_check", get_final_url))
    
    # 启动 Webhook
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
