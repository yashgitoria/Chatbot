import os, logging, sys

API_ID = 17963091
API_HASH = "cd65e421232d0a205426e5e015dc9acd"
BOT_TOKEN = "8653490458:AAFOoGhpbtYCTfzt5QvWBXR4gtyUKKoLKGA"

DB_URI = os.environ.get("DATABASE_URL", "mongodb+srv://ronak:ronak@cluster0.s42kf.mongodb.net/?retryWrites=true&w=majority&appName=Cluster0")
DB_NAME = os.environ.get("DATABASE_NAME", "midnight-yash")

# PORT = 6000
OWNER_ID = 8940899601
ADMINS = [OWNER_ID,7533800542, 8525282889, 8114435360, 8349410880]
TG_BOT_WORKERS = 4

VERIFY_EXPIRE = 12 * 3600
DB_ID = -1003849339538
CHANNEL_ID = -1003849339538
waiting_timer_status = False
REFERRAL_REWARD_DAYS = 1
START_ID = 34
END_ID = 40000
BYPASS_LIMIT = 1

PICS = os.getenv(
    "PICS",
    "https://i.ibb.co/Kjd5qt9r/demon-slayer-3840x2160-23247.jpg "
    "https://i.ibb.co/mryY4Swx/zenitsu-agatsuma-3840x2160-24346.jpg "
    "https://i.postimg.cc/nVWGBq25/zenitsu-agatsuma-3840x2160-19143.jpg "
    "https://i.postimg.cc/SKm6kdS5/zenitsu-agatsuma-3840x2160-17045.jpg "
    "https://i.postimg.cc/CKvm2XG2/zenitsu-agatsuma-3840x2160-17046.jpg"
).split()


commands = [
    "start","help","myplan","refer","id","set_free_limit","reset_free_count","update",
    "verification","admin","free","toggle_refer","check_refers","addadmin","deladmin",
    "listadmin","stats","ban","unban","dbroadcast","broadcast","listfsub","delfsub",
    "addfsub","del_shortner","list_shortner","add_shortner","status","addpaid",'scrapper',
    "removepaid","listpaid","restart","set","cleanup","adddump","deldump",'migrate','genlink',
    "listdump","layout","hmanga","waiting_timer","batch","video","envelope",'banlist','listban','link','restricted','r'
]

ADMIN_CMD = [
    "set_free_limit","reset_free_count","update","genlink","batch","scrapper",
    "waiting_timer","verification","admin","free","toggle_refer","check_refers",
    "addadmin","deladmin","listadmin","stats","ban","unban","dbroadcast","broadcast",
    "listfsub","delfsub","addfsub","del_shortner","list_shortner","add_shortner",
    "status","addpaid","removepaid","listpaid","restart","set","cleanup",
    "adddump","deldump","listdump","layout","hmanga","envelope",'banlist','listban','dw','genlink'
]
# ------------------ PAYMENT ACCOUNTS ------------------

PAYMENT_ACCOUNTS = {
    "ronak": {
        "upi": "paytm.s2vv3il@pty",
        "merchant": "sPATsm39982251499052"
    },
    "kartik": {
        "upi": "paytm.s1ms8ba@pty",
        "merchant": "YPfQEi05426608236469"
    }
}

# Default account
ACTIVE_PAYMENT = "yash"
# UPI_ID = ""
# MERCHANT_ID = ""

PLANS = [
    {"days": 1,   "price": "₹15"},     # impulse / emergency
    {"days": 7,   "price": "₹59"},     # trial (59×4 = 236)
    {"days": 30,  "price": "₹129"},    # most popular
    {"days": 90,  "price": "₹279"},    # strong value
    {"days": 180, "price": "₹449"},    # long-term saver
    {"days": 365, "price": "₹749"},    # best value
]

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)
logging.getLogger("pyrogram").setLevel(logging.WARNING)
LOGGER = lambda name: logging.getLogger(name)
