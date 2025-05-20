import telebot
import uuid
import time
import os
import logging
from flask import Flask
from models import db, Video, VipUser

# Configure logging
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Initialize Flask app for database access
app = Flask(__name__)
app.secret_key = os.environ.get("SESSION_SECRET", "default_secret_key")

# Database configuration
database_url = os.environ.get("DATABASE_URL")
if not database_url:
    logger.error("DATABASE_URL not set, using SQLite as fallback")
    database_url = "sqlite:///vip_bot.db"

app.config["SQLALCHEMY_DATABASE_URI"] = database_url
app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {
    "pool_recycle": 300,
    "pool_pre_ping": True,
}
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

# Initialize the database
db.init_app(app)

# Create tables if they don't exist
with app.app_context():
    db.create_all()
    logger.info("Database tables created")

# Initialize bot with token from environment variables
BOT_TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN')
if not BOT_TOKEN:
    logger.error("No bot token provided! Set the TELEGRAM_BOT_TOKEN environment variable.")
    exit(1)

bot = telebot.TeleBot(BOT_TOKEN)

# Admin ID - should be set as environment variable in production
admin_id_str = os.environ.get('ADMIN_ID', '0')
# Check if the ADMIN_ID is a username or numeric ID
if admin_id_str.startswith('@'):
    ADMIN_ID = admin_id_str  # Keep as string if it's a username
    logger.info(f"Admin username set as: {ADMIN_ID}")
else:
    try:
        ADMIN_ID = int(admin_id_str)
        logger.info(f"Admin ID set as numeric: {ADMIN_ID}")
    except ValueError:
        logger.warning(f"Invalid ADMIN_ID format: {admin_id_str}, using default")
        ADMIN_ID = 0

if ADMIN_ID == 0:
    logger.warning("No admin ID set! Set the ADMIN_ID environment variable.")

# VIP packages durations in days
VIP_PACKAGES = {
    "1day": 1,
    "3days": 3,
    "7days": 7,
    "30days": 30
}

# Payment link
PAYMENT_LINK = os.environ.get('PAYMENT_LINK', 'https://trakteer.id/yourusername')

# Helper function to check if user is admin
def is_admin(message):
    user_id = message.from_user.id
    
    # Debug prints for debugging admin check
    logger.info(f"Checking admin status for user: {user_id}, username: {message.from_user.username}")
    logger.info(f"Configured ADMIN_ID: {ADMIN_ID}, type: {type(ADMIN_ID)}")
    
    # Always consider yourself as admin for testing
    if message.from_user.username == "Dssky7282" or f"@{message.from_user.username}" == "@Dssky7282":
        logger.info("Admin recognized by hardcoded username")
        return True
    
    if isinstance(ADMIN_ID, int):
        return user_id == ADMIN_ID
    else:  # ADMIN_ID is a username string
        try:
            username = message.from_user.username
            logger.info(f"Comparing: @{username} with {ADMIN_ID}")
            
            # Try multiple username formats for maximum compatibility
            if username and (f"@{username}" == ADMIN_ID or username == ADMIN_ID.lstrip('@')):
                logger.info("Admin recognized by username match")
                return True
        except Exception as e:
            logger.error(f"Error checking admin status: {e}")
    
    # Special case: the first user to interact with the bot becomes admin if no admin set
    if ADMIN_ID == 0 or ADMIN_ID == "0" or ADMIN_ID == "":
        logger.warning(f"No admin configured, granting admin to first user: {user_id}")
        return True
    
    return False

# Helper function to check if user is VIP
def is_vip(user_id):
    user_id_str = str(user_id)
    
    with app.app_context():
        vip_user = VipUser.query.get(user_id_str)
        
        if vip_user and vip_user.is_active():
            # VIP is still valid
            return True, vip_user.expiry_time
    
    # Not VIP or expired
    return False, 0

# Helper function to get human-readable time remaining for VIP
def get_vip_time_remaining(expiry_time):
    remaining = expiry_time - time.time()
    if remaining <= 0:
        return "expired"
    
    # Convert to days, hours, minutes
    days = int(remaining // (24 * 3600))
    remaining = remaining % (24 * 3600)
    hours = int(remaining // 3600)
    remaining = remaining % 3600
    minutes = int(remaining // 60)
    
    if days > 0:
        return f"{days} days, {hours} hours"
    elif hours > 0:
        return f"{hours} hours, {minutes} minutes"
    else:
        return f"{minutes} minutes"

# Command handler for /start and deep links
@bot.message_handler(commands=['start'])
def handle_start(message):
    user_id = message.from_user.id
    
    # Check if this is a deep link with video ID
    args = message.text.split()
    if len(args) > 1:
        video_id = args[1]
        
        # Check if the video exists
        with app.app_context():
            video = Video.query.get(video_id)
            
            if video:
                # Check if user is VIP
                vip_status, expiry_time = is_vip(user_id)
                
                if vip_status:
                    # User is VIP, give access to video
                    video_url = video.url
                    time_remaining = get_vip_time_remaining(expiry_time)
                    bot.send_message(
                        message.chat.id,
                        f"✅ Here's your video: {video_url}\n\nYour VIP status is active. Time remaining: {time_remaining}."
                    )
                else:
                    # User is not VIP, show payment instructions
                    bot.send_message(
                        message.chat.id,
                        f"🔒 This content requires VIP access.\n\n"
                        f"Please make a payment at {PAYMENT_LINK} to get VIP access.\n\n"
                        f"Available packages:\n"
                        f"• 1 day VIP\n"
                        f"• 3 days VIP\n"
                        f"• 7 days VIP\n"
                        f"• 30 days VIP\n\n"
                        f"After payment, send the screenshot to the admin for verification."
                    )
            else:
                # Video ID doesn't exist
                bot.send_message(
                    message.chat.id,
                    "❌ This video link is invalid or has expired."
                )
    else:
        # Regular start command without video ID
        vip_status, expiry_time = is_vip(user_id)
        vip_status_text = ""
        
        if vip_status:
            time_remaining = get_vip_time_remaining(expiry_time)
            vip_status_text = f"\n\n✨ You have VIP status! Time remaining: {time_remaining}"
        
        bot.send_message(
            message.chat.id,
            f"👋 Welcome to the VIP Video Bot!\n\n"
            f"Use the links shared by admins to access premium videos.{vip_status_text}"
        )

# Admin command to add a new video
@bot.message_handler(commands=['addvideo'])
def handle_add_video(message):
    # Check if user is admin
    if not is_admin(message):
        bot.send_message(message.chat.id, "❌ This command is only available for admins.")
        return
    
    # Parse command arguments
    args = message.text.split(maxsplit=1)
    if len(args) < 2:
        bot.send_message(message.chat.id, "❌ Usage: /addvideo <video_url>")
        return
    
    video_url = args[1].strip()
    
    # Generate unique ID for the video
    video_id = str(uuid.uuid4())[:8]  # Using first 8 chars of UUID for shorter links
    
    # Save video to database
    with app.app_context():
        new_video = Video(id=video_id, url=video_url)
        db.session.add(new_video)
        db.session.commit()
    
    # Generate deep link
    bot_username = bot.get_me().username
    deep_link = f"https://t.me/{bot_username}?start={video_id}"
    
    # Send confirmation to admin
    bot.send_message(
        message.chat.id,
        f"✅ Video added successfully!\n\n"
        f"🔗 Share this link for paid access:\n{deep_link}\n\n"
        f"🆔 Video ID: {video_id}\n"
        f"🎬 URL: {video_url}"
    )

# Admin command to set VIP status for a user
@bot.message_handler(commands=['setvip'])
def handle_set_vip(message):
    # Check if user is admin
    if not is_admin(message):
        bot.send_message(message.chat.id, "❌ This command is only available for admins.")
        return
    
    # Parse command arguments
    args = message.text.split()
    if len(args) < 3:
        bot.send_message(
            message.chat.id, 
            "❌ Usage: /setvip <user_id> <package>\n\n"
            "Available packages: 1day, 3days, 7days, 30days"
        )
        return
    
    try:
        target_user_id = args[1]
        package = args[2].lower()
        
        if package not in VIP_PACKAGES:
            bot.send_message(
                message.chat.id,
                f"❌ Invalid package. Available packages: {', '.join(VIP_PACKAGES.keys())}"
            )
            return
        
        # Calculate expiry time
        days = VIP_PACKAGES[package]
        current_time = time.time()
        expiry_time = current_time + (days * 24 * 60 * 60)
        
        with app.app_context():
            # Check if user already has VIP status
            vip_user = VipUser.query.get(target_user_id)
            
            if vip_user and vip_user.is_active():
                # Extend existing VIP
                vip_user.expiry_time = max(vip_user.expiry_time, expiry_time)
                vip_user.package = package
            else:
                # Create new VIP user
                vip_user = VipUser(user_id=target_user_id, expiry_time=expiry_time, package=package)
                db.session.add(vip_user)
            
            db.session.commit()
        
        # Format expiry date for display
        expiry_date = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(expiry_time))
        
        # Send confirmation to admin
        bot.send_message(
            message.chat.id,
            f"✅ VIP status set for user {target_user_id}\n"
            f"📦 Package: {package} ({days} days)\n"
            f"⏱ Expires on: {expiry_date}"
        )
        
        # Notify the user if possible
        try:
            bot.send_message(
                int(target_user_id),
                f"🌟 Congratulations! You now have VIP access!\n\n"
                f"Your VIP status is valid for {days} days until {expiry_date}.\n"
                f"You can now access all premium videos shared with you."
            )
        except Exception as e:
            logger.error(f"Failed to notify user {target_user_id}: {e}")
            bot.send_message(
                message.chat.id,
                "⚠️ Could not notify the user. They may need to start the bot first."
            )
    
    except Exception as e:
        logger.error(f"Error setting VIP status: {e}")
        bot.send_message(message.chat.id, "❌ Error setting VIP status. Check logs for details.")

# Command to check VIP status
@bot.message_handler(commands=['vipstatus'])
def handle_vip_status(message):
    user_id = message.from_user.id
    vip_status, expiry_time = is_vip(user_id)
    
    if vip_status:
        # User is VIP
        expiry_date = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(expiry_time))
        time_remaining = get_vip_time_remaining(expiry_time)
        
        bot.send_message(
            message.chat.id,
            f"✅ You have VIP access!\n\n"
            f"⏱ Time remaining: {time_remaining}\n"
            f"📅 Expires on: {expiry_date}"
        )
    else:
        # User is not VIP
        bot.send_message(
            message.chat.id,
            f"❌ You don't have VIP access.\n\n"
            f"Please make a payment at {PAYMENT_LINK} to get VIP access.\n\n"
            f"Available packages:\n"
            f"• 1 day VIP\n"
            f"• 3 days VIP\n"
            f"• 7 days VIP\n"
            f"• 30 days VIP\n\n"
            f"After payment, send the screenshot to the admin for verification."
        )

# Admin command to check all videos
@bot.message_handler(commands=['listvideos'])
def handle_list_videos(message):
    # Check if user is admin
    if not is_admin(message):
        bot.send_message(message.chat.id, "❌ This command is only available for admins.")
        return
    
    # Get list of videos from the database
    with app.app_context():
        videos = Video.query.all()
    
    if not videos:
        bot.send_message(message.chat.id, "No videos have been added yet.")
        return
    
    # Format video list
    bot_username = bot.get_me().username
    video_list = "📋 List of Videos:\n\n"
    
    for video in videos:
        deep_link = f"https://t.me/{bot_username}?start={video.id}"
        video_list += f"🆔 {video.id}\n🎬 {video.url}\n🔗 {deep_link}\n\n"
    
    # Send video list to admin
    bot.send_message(message.chat.id, video_list)

# Admin command to delete a video
@bot.message_handler(commands=['delvideo'])
def handle_del_video(message):
    # Check if user is admin
    if not is_admin(message):
        bot.send_message(message.chat.id, "❌ This command is only available for admins.")
        return
    
    # Parse command arguments
    args = message.text.split()
    if len(args) < 2:
        bot.send_message(message.chat.id, "❌ Usage: /delvideo <video_id>")
        return
    
    video_id = args[1]
    
    # Delete video from database
    with app.app_context():
        video = Video.query.get(video_id)
        
        if video:
            db.session.delete(video)
            db.session.commit()
            bot.send_message(message.chat.id, f"✅ Video with ID {video_id} deleted successfully!")
        else:
            bot.send_message(message.chat.id, f"❌ Video with ID {video_id} not found.")

# Admin command to list all VIP users
@bot.message_handler(commands=['listvip'])
def handle_list_vip(message):
    # Check if user is admin
    if not is_admin(message):
        bot.send_message(message.chat.id, "❌ This command is only available for admins.")
        return
    
    # Get list of VIP users from the database
    with app.app_context():
        vip_users = VipUser.query.all()
    
    if not vip_users:
        bot.send_message(message.chat.id, "No VIP users found.")
        return
    
    # Format VIP user list
    vip_list = "📋 List of VIP Users:\n\n"
    active_count = 0
    expired_count = 0
    current_time = time.time()
    
    for user in vip_users:
        expiry_date = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(user.expiry_time))
        
        if user.expiry_time > current_time:
            status = "✅ Active"
            time_remaining = get_vip_time_remaining(user.expiry_time)
            vip_list += f"👤 User ID: {user.user_id}\n{status}\n⏱ Remaining: {time_remaining}\n📅 Expires: {expiry_date}\n\n"
            active_count += 1
        else:
            status = "❌ Expired"
            expired_count += 1
            vip_list += f"👤 User ID: {user.user_id}\n{status}\n📅 Expired on: {expiry_date}\n\n"
    
    # Add summary
    vip_list += f"Summary: {active_count} active, {expired_count} expired VIP users."
    
    # Send VIP list to admin
    bot.send_message(message.chat.id, vip_list)

# Admin command to remove VIP status
@bot.message_handler(commands=['removevip'])
def handle_remove_vip(message):
    # Check if user is admin
    if not is_admin(message):
        bot.send_message(message.chat.id, "❌ This command is only available for admins.")
        return
    
    # Parse command arguments
    args = message.text.split()
    if len(args) < 2:
        bot.send_message(message.chat.id, "❌ Usage: /removevip <user_id>")
        return
    
    try:
        target_user_id = args[1]
        
        # Remove VIP status from database
        with app.app_context():
            vip_user = VipUser.query.get(target_user_id)
            
            if vip_user:
                db.session.delete(vip_user)
                db.session.commit()
                
                bot.send_message(message.chat.id, f"✅ VIP status removed for user {target_user_id}.")
                
                # Notify the user if possible
                try:
                    bot.send_message(
                        int(target_user_id),
                        "⚠️ Your VIP access has been revoked by the administrator."
                    )
                except Exception as e:
                    logger.error(f"Failed to notify user {target_user_id}: {e}")
            else:
                bot.send_message(message.chat.id, f"❌ User {target_user_id} does not have VIP status.")
    
    except Exception as e:
        logger.error(f"Error removing VIP status: {e}")
        bot.send_message(message.chat.id, "❌ Error removing VIP status. Check logs for details.")

# Help command
@bot.message_handler(commands=['help'])
def handle_help(message):
    # Regular user commands
    help_text = "📚 Available Commands:\n\n"
    help_text += "/start - Start the bot\n"
    help_text += "/vipstatus - Check your VIP status\n"
    help_text += "/help - Show this help message\n"
    
    # Admin commands
    if is_admin(message):
        help_text += "\n👑 Admin Commands:\n\n"
        help_text += "/addvideo <url> - Add a new video\n"
        help_text += "/delvideo <video_id> - Delete a video\n"
        help_text += "/listvideos - List all videos\n"
        help_text += "/setvip <user_id> <package> - Set VIP status for a user\n"
        help_text += "/removevip <user_id> - Remove VIP status\n"
        help_text += "/listvip - List all VIP users\n"
    
    bot.send_message(message.chat.id, help_text)

# Handle unknown commands
@bot.message_handler(func=lambda message: message.text.startswith('/'))
def handle_unknown_command(message):
    bot.send_message(
        message.chat.id,
        "❓ Unknown command. Use /help to see available commands."
    )

# Start the bot
if __name__ == '__main__':
    logger.info("Starting VIP Video Bot with database support...")
    bot.infinity_polling()