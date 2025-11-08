import os
import logging
import requests
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

# 配置日志记录
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', 
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# --- 核心功能函数 ---
async def get_final_url(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    # 替换成您要追踪的域名 A
    DOMAIN_A = "http://your-dynamic-domain-a.com" 
    
    await update.message.reply_text("正在为您获取最终动态链接，请稍候...")
    
    try:
        # 发起请求并自动跟踪重定向
        # 确保每次请求都得到最新的重定向结果
        response = requests.get(DOMAIN_A, allow_redirects=True, timeout=10)
        
        # 检查是否成功
        if response.status_code == 200 or 300 <= response.status_code < 400:
            # response.url 是最终重定向后的 URL (域名 B)
            final_url_b = response.url
            
            await update.message.reply_text(f"✅ 最终动态域名 B 是：\n{final_url_b}")
        else:
            await update.message.reply_text(f"❌ 链接获取失败，域名 A 返回了状态码: {response.status_code}")
            logger.error(f"Request failed with status code {response.status_code} for {DOMAIN_A}")
            
    except requests.exceptions.RequestException as e:
        await update.message.reply_text(f"❌ 链接获取失败，出现网络错误。")
        logger.error(f"Request Error: {e}")

# --- Webhook 主函数 ---
def main() -> None:
    # 从 Render 环境变量中获取配置
    TOKEN = os.environ.get("TELEGRAM_TOKEN")
    
    # Render 会自动设置外部 URL 和端口
    WEBHOOK_URL = os.environ.get("RENDER_EXTERNAL_URL")
    PORT = int(os.environ.get("PORT", 8080))

    if not TOKEN or not WEBHOOK_URL:
        logger.error("TELEGRAM_TOKEN or RENDER_EXTERNAL_URL is not set. Exiting.")
        return

    # 完整 Webhook 地址 (注意路径 /telegram 必须与 run_webhook 的 url_path 匹配)
    full_webhook_url = f"{WEBHOOK_URL}/telegram"
    
    # 1. 构建 Application
    application = Application.builder().token(TOKEN).build()

    # 2. 注册命令处理器：用户发送 /start_check 时触发
    application.add_handler(CommandHandler("start_check", get_final_url))
    
    # 3. 设置 Webhook 到 Telegram
    # 只需要设置 Webhook 的基础 URL，path 会自动处理
    application.run_webhook(
        listen="0.0.0.0",
        port=PORT,
        url_path="/telegram",
        webhook_url=full_webhook_url,
    )
    
    logger.info(f"Webhook started successfully at {full_webhook_url}")

if __name__ == "__main__":
    main()