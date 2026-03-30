"""
Generate synthetic retail grocery data and write to Unity Catalog tables.
(Japanese localized version — domain data literals adapted for Japan)

Usage:
    Run as a Databricks notebook or via `databricks` CLI:
        databricks jobs submit --json '{"notebook_task": {"notebook_path": "..."}}'

    Or locally with PySpark + Unity Catalog connectivity.

Target schema: <CATALOG>.<SCHEMA>
"""

import json
import random
from datetime import datetime, timedelta

from pyspark.sql import SparkSession
from pyspark.sql import functions as F
from pyspark.sql.types import (
    ArrayType,
    DecimalType,
    DoubleType,
    IntegerType,
    StringType,
    StructField,
    StructType,
    TimestampType,
)

# ── TO DO Change the ──────────────────────────────────────────────────────────
CATALOG = "qsic_workshop_prep_catalog"
SCHEMA = "retail_agent"
FULL_SCHEMA = f"{CATALOG}.{SCHEMA}"

spark = SparkSession.builder.getOrCreate()
spark.sql(f"CREATE SCHEMA IF NOT EXISTS {FULL_SCHEMA}")

random.seed(42)

# ── Domain data ─────────────────────────────────────────────────────
FIRST_NAMES = [
    "太郎", "花子", "一郎", "美咲", "健太", "さくら", "大輔", "陽子",
    "翔太", "真由美", "直樹", "恵子", "雄大", "由美", "拓也", "愛",
    "和也", "裕子", "達也", "明美", "浩二", "久美子", "誠", "典子",
    "隆", "智子", "剛", "幸子", "学", "麻衣", "哲也", "香織",
    "秀樹", "理恵", "正人", "友美", "康介", "恵美", "勇気", "瞳",
    "修", "奈々", "亮", "彩", "渉", "舞", "悠太", "葵",
    "圭介", "結衣", "裕介", "美穂", "慎一", "沙織", "俊介", "千尋",
    "大地", "真理", "光", "美紀", "蓮", "遥", "颯太", "凛",
    "陸", "杏", "海斗", "楓", "春樹", "莉子", "悠斗", "琴音",
    "樹", "菜々子", "蒼", "桃花", "陽", "七海", "新", "日菜",
    "湊", "茜", "朝陽", "小春", "壮太", "美月", "響", "紬",
    "暖", "柚希", "律", "ひなた", "晴", "芽依", "奏", "澪",
]

LAST_NAMES = [
    "佐藤", "鈴木", "高橋", "田中", "伊藤", "渡辺", "山本", "中村",
    "小林", "加藤", "吉田", "山田", "佐々木", "松本", "井上", "木村",
    "林", "斎藤", "清水", "山口", "池田", "橋本", "阿部", "石川",
    "前田", "藤田", "小川", "岡田", "後藤", "長谷川", "村上", "近藤",
    "石井", "坂本", "遠藤", "青木", "藤井", "西村", "福田", "太田",
    "三浦", "藤原", "岡本", "中島", "松田", "中野", "原田", "小野",
    "田村", "竹内",
]

STREETS = [
    "中央", "本町", "栄町", "緑町", "桜丘", "若葉台", "松原",
    "青山", "日の出", "丘の上", "泉", "旭", "花見川",
    "春日", "梅園", "朝日", "富士見", "光が丘", "新町",
    "港南",
]

CITIES_STATES = [
    ("東京都千代田区", "東京都"), ("横浜市西区", "神奈川県"), ("大阪市北区", "大阪府"), ("名古屋市中区", "愛知県"),
    ("札幌市中央区", "北海道"), ("福岡市博多区", "福岡県"), ("仙台市青葉区", "宮城県"), ("広島市中区", "広島県"),
    ("京都市中京区", "京都府"), ("神戸市中央区", "兵庫県"), ("さいたま市大宮区", "埼玉県"), ("千葉市中央区", "千葉県"),
    ("新潟市中央区", "新潟県"), ("静岡市葵区", "静岡県"), ("金沢市", "石川県"),
]

MEMBERSHIP_TIERS = ["Bronze", "Silver", "Gold", "Platinum"]
DIETARY_PREFS = ["ベジタリアン", "ヴィーガン", "グルテンフリー", "低糖質", "無添加", "乳製品不使用", "ナッツフリー", "なし"]
FAVORITE_CATEGORIES = ["青果", "乳製品", "ベーカリー", "精肉・鮮魚", "冷凍食品", "お菓子", "飲料", "惣菜", "オーガニック"]
PAYMENT_METHODS = ["credit_card", "debit_card", "cash", "mobile_pay", "gift_card"]

# Product catalog by category
PRODUCTS_BY_CATEGORY = {
    "青果": [
        ("有機バナナ", "ドール", 198, "房"), ("ふじりんご", "青森産", 298, "個"),
        ("ベビーリーフ", "サラダクラブ", 198, "袋"), ("アボカド", "メキシコ産", 148, "個"),
        ("トマト", "熊本産", 298, "パック"), ("ブルーベリー", "チリ産", 498, "パック"),
        ("さつまいも", "鳴門金時", 198, "本"), ("ブロッコリー", "国産", 248, "株"),
        ("いちご", "あまおう", 598, "パック"), ("レモン", "広島産", 98, "個"),
        ("きゅうり", "国産", 98, "本"), ("パプリカ", "韓国産", 168, "個"),
        ("にんじん", "北海道産", 158, "袋"), ("じゃがいも", "北海道産", 298, "袋"),
        ("カット野菜ミックス", "サラダクラブ", 198, "袋"), ("巨峰", "長野産", 498, "パック"),
    ],
    "乳製品": [
        ("おいしい牛乳", "明治", 268, "1L"), ("低脂肪乳", "森永", 178, "1L"),
        ("ギリシャヨーグルト", "パルテノ", 178, "個"), ("とろけるチーズ", "雪印", 298, "袋"),
        ("北海道バター", "よつ葉", 398, "200g"), ("生クリーム", "タカナシ", 298, "200ml"),
        ("サワークリーム", "中沢", 298, "180ml"), ("クリームチーズ", "フィラデルフィア", 348, "200g"),
        ("モッツァレラチーズ", "森永", 398, "100g"), ("アーモンドミルク", "グリコ", 298, "1L"),
        ("オーツミルク", "マイナーフィギュアズ", 398, "1L"), ("カッテージチーズ", "雪印", 298, "200g"),
        ("パルメザンチーズ", "クラフト", 498, "80g"), ("たまご", "ヨード卵光", 298, "10個入"),
    ],
    "ベーカリー": [
        ("食パン", "超熟", 178, "6枚切"), ("全粒粉食パン", "パスコ", 228, "6枚切"),
        ("クロワッサン", "店内焼き", 128, "個"), ("ベーグル", "店内焼き", 168, "個"),
        ("フランスパン", "店内焼き", 248, "本"), ("シナモンロール", "店内焼き", 198, "個"),
        ("ナン", "デルソーレ", 298, "3枚入"), ("バーガーバンズ", "店内焼き", 198, "4個入"),
        ("ライ麦パン", "店内焼き", 298, "1斤"), ("ロールパン", "ネオバターロール", 178, "6個入"),
    ],
    "精肉・鮮魚": [
        ("鶏むね肉", "国産", 98, "100g"), ("豚ひき肉", "国産", 128, "100g"),
        ("銀鮭切身", "チリ産", 298, "2切"), ("豚ロース", "国産", 178, "100g"),
        ("ベーコン", "日本ハム", 298, "4枚入"), ("むきえび", "インドネシア産", 498, "200g"),
        ("牛切り落とし", "国産", 298, "100g"), ("あらびきウインナー", "シャウエッセン", 398, "2袋入"),
        ("和牛サーロイン", "A5ランク", 1980, "100g"), ("鶏ひき肉", "国産", 88, "100g"),
        ("まぐろ刺身", "太平洋産", 498, "柵"), ("ラムチョップ", "NZ産", 598, "100g"),
    ],
    "冷凍食品": [
        ("冷凍ピザ マルゲリータ", "明治", 498, "枚"), ("バニラアイス", "ハーゲンダッツ", 298, "個"),
        ("冷凍野菜ミックス", "ニチレイ", 198, "袋"), ("冷凍ミックスベリー", "トロピカルマリア", 398, "袋"),
        ("冷凍たこ焼き", "ニッスイ", 298, "袋"), ("冷凍餃子", "味の素", 248, "12個入"),
        ("冷凍コロッケ", "ニチレイ", 198, "4個入"), ("冷凍枝豆", "ニチレイ", 178, "袋"),
        ("アイスバー", "ガリガリ君", 78, "本"), ("冷凍グラタン", "ニチレイ", 298, "個"),
    ],
    "お菓子": [
        ("ポテトチップス うすしお", "カルビー", 148, "袋"), ("ミックスナッツ", "稲葉", 498, "袋"),
        ("グラノーラバー", "アサヒ", 198, "箱"), ("プリッツ", "グリコ", 128, "箱"),
        ("チョコレート", "明治", 198, "箱"), ("ポップコーン", "マイクポップコーン", 128, "袋"),
        ("おせんべい", "亀田製菓", 198, "袋"), ("柿の種", "亀田製菓", 248, "袋"),
        ("ミックスナッツ 大容量", "稲葉", 898, "缶"), ("おかき", "岩塚製菓", 178, "袋"),
        ("じゃがりこ", "カルビー", 158, "カップ"), ("果汁グミ", "明治", 128, "袋"),
    ],
    "飲料": [
        ("オレンジジュース", "トロピカーナ", 248, "1L"), ("炭酸水 レモン", "ウィルキンソン", 88, "500ml"),
        ("ドリップコーヒー", "UCC", 498, "袋"), ("緑茶ティーバッグ", "伊藤園", 298, "箱"),
        ("ほうじ茶", "伊藤園", 148, "500ml"), ("りんごジュース", "青森りんご", 198, "1L"),
        ("アイスコーヒー", "UCC", 178, "1L"), ("ココナッツウォーター", "Vita Coco", 248, "330ml"),
        ("カルピスウォーター", "アサヒ", 128, "500ml"), ("スポーツドリンク", "ポカリスエット", 158, "500ml"),
    ],
    "食品・調味料": [
        ("エキストラバージンオリーブオイル", "ボスコ", 698, "本"), ("スパゲッティ", "マ・マー", 198, "袋"),
        ("トマトソース", "カゴメ", 298, "瓶"), ("コシヒカリ", "新潟産", 2180, "5kg"),
        ("大豆水煮", "いなば", 128, "缶"), ("鶏がらスープの素", "味の素", 198, "瓶"),
        ("ごはんですよ", "桃屋", 298, "瓶"), ("はちみつ", "サクラ印", 598, "瓶"),
        ("ツナ缶", "いなば", 128, "缶"), ("ココナッツミルク", "ユウキ食品", 198, "缶"),
        ("みりん", "タカラ", 298, "500ml"), ("薄力粉", "日清", 198, "1kg"),
        ("上白糖", "三井製糖", 198, "1kg"), ("醤油", "キッコーマン", 298, "1L"),
    ],
    "惣菜": [
        ("チキン南蛮", "店内調理", 498, "パック"), ("ハムカツ", "店内調理", 298, "パック"),
        ("ポテトサラダ", "店内調理", 298, "パック"), ("チキンサラダ", "店内調理", 398, "パック"),
        ("マカロニサラダ", "店内調理", 248, "パック"), ("ローストチキン", "店内調理", 598, "個"),
        ("ひじき煮", "店内調理", 198, "パック"), ("きんぴらごぼう", "店内調理", 198, "パック"),
    ],
    "日用品": [
        ("キッチンペーパー", "エリエール", 298, "4ロール"), ("食器用洗剤", "キュキュット", 198, "本"),
        ("ゴミ袋", "ジャパックス", 298, "30枚入"), ("洗濯洗剤", "アタック", 398, "本"),
        ("アルミホイル", "東洋アルミ", 178, "ロール"), ("スポンジ", "スコッチブライト", 198, "3個入"),
        ("ジップロック", "旭化成", 298, "15枚入"), ("住居用洗剤", "ウタマロクリーナー", 398, "本"),
    ],
}

STORE_NAMES = [
    "フレッシュマート 渋谷店", "フレッシュマート 新宿店", "フレッシュマート 池袋店",
    "フレッシュマート 横浜店", "フレッシュマート 大阪梅田店", "フレッシュマート 名古屋栄店",
    "フレッシュマート 札幌店", "フレッシュマート 福岡天神店", "フレッシュマート 仙台店",
    "フレッシュマート 広島店",
]


def random_phone():
    area = random.choice(["03", "06", "011", "052", "045", "092", "022", "082", "075", "078"])
    return f"{area}-{random.randint(1000,9999)}-{random.randint(1000,9999)}"


def random_email(first, last):
    domains = ["gmail.com", "yahoo.co.jp", "outlook.jp", "icloud.com", "docomo.ne.jp"]
    sep = random.choice([".", "_", ""])
    num = random.choice(["", str(random.randint(1, 99))])
    # Use a simple hash-based approach for consistent romanization
    import hashlib
    name_hash = hashlib.md5(f"{first}{last}".encode()).hexdigest()[:8]
    return f"user{sep}{name_hash}{num}@{random.choice(domains)}"


def random_zip():
    return f"{random.randint(100, 999)}-{random.randint(1000, 9999)}"


# ── 1. Customers ───────────────────────────────────────────────────
print("Generating customers...")
customers = []
for i in range(1, 201):
    first = random.choice(FIRST_NAMES)
    last = random.choice(LAST_NAMES)
    city, state = random.choice(CITIES_STATES)
    prefs = {
        "dietary": random.sample(DIETARY_PREFS, k=random.randint(0, 2)),
        "favorite_categories": random.sample(FAVORITE_CATEGORIES, k=random.randint(1, 3)),
        "organic_preference": random.choice([True, False]),
    }
    customers.append({
        "customer_id": f"CUST-{i:04d}",
        "first_name": first,
        "last_name": last,
        "email": random_email(first, last),
        "phone": random_phone(),
        "address": f"{random.choice(STREETS)}{random.randint(1,30)}-{random.randint(1,20)}-{random.randint(1,15)}",
        "city": city,
        "state": state,
        "zip_code": random_zip(),
        "membership_tier": random.choices(MEMBERSHIP_TIERS, weights=[40, 30, 20, 10])[0],
        "join_date": (datetime(2020, 1, 1) + timedelta(days=random.randint(0, 1800))).strftime("%Y-%m-%d"),
        "preferences": json.dumps(prefs),
    })

customers_df = spark.createDataFrame(customers)
customers_df.write.mode("overwrite").saveAsTable(f"{FULL_SCHEMA}.customers")
print(f"  Wrote {customers_df.count()} customers")

# ── 2. Products ─────────────────────────────────────────────────────
print("Generating products...")
products = []
pid = 1
aisles = {}
aisle_num = 1
for cat in PRODUCTS_BY_CATEGORY:
    if cat not in aisles:
        aisles[cat] = aisle_num
        aisle_num += 1
    for name, brand, price, unit in PRODUCTS_BY_CATEGORY[cat]:
        products.append({
            "product_id": f"PROD-{pid:04d}",
            "name": name,
            "category": cat,
            "brand": brand,
            "price": round(price, 2),
            "stock_quantity": random.randint(0, 500),
            "aisle": aisles[cat],
            "unit": unit,
        })
        pid += 1

# Pad to ~500 products with variations
while len(products) < 500:
    cat = random.choice(list(PRODUCTS_BY_CATEGORY.keys()))
    base = random.choice(PRODUCTS_BY_CATEGORY[cat])
    variation = random.choice(["有機 ", "大容量 ", "お徳用 ", "プレミアム ", "ライト "])
    products.append({
        "product_id": f"PROD-{pid:04d}",
        "name": f"{variation}{base[0]}",
        "category": cat,
        "brand": base[1],
        "price": round(base[2] * random.uniform(0.8, 1.5), 2),
        "stock_quantity": random.randint(0, 500),
        "aisle": aisles[cat],
        "unit": base[3],
    })
    pid += 1

products_df = spark.createDataFrame(products)
products_df.write.mode("overwrite").saveAsTable(f"{FULL_SCHEMA}.products")
print(f"  Wrote {products_df.count()} products")

# ── 3. Stores ───────────────────────────────────────────────────────
print("Generating stores...")
stores = []
for i, name in enumerate(STORE_NAMES, 1):
    city, state = CITIES_STATES[i % len(CITIES_STATES)]
    stores.append({
        "store_id": f"STORE-{i:02d}",
        "name": name,
        "address": f"{random.choice(STREETS)}{random.randint(1,30)}-{random.randint(1,20)}-{random.randint(1,15)}",
        "city": city,
        "state": state,
        "zip_code": random_zip(),
        "hours": "9:00～22:00",
        "phone": random_phone(),
    })

stores_df = spark.createDataFrame(stores)
stores_df.write.mode("overwrite").saveAsTable(f"{FULL_SCHEMA}.stores")
print(f"  Wrote {stores_df.count()} stores")

# ── 4. Transactions + Transaction Items ─────────────────────────────
print("Generating transactions and transaction items...")
transactions = []
transaction_items = []
item_id = 1

for txn_id in range(1, 2001):
    customer = random.choice(customers)
    store = random.choice(stores)
    txn_date = datetime(2024, 1, 1) + timedelta(
        days=random.randint(0, 440),
        hours=random.randint(7, 21),
        minutes=random.randint(0, 59),
    )
    num_items = random.randint(2, 8)
    txn_products = random.sample(products, k=min(num_items, len(products)))

    total = 0.0
    for prod in txn_products:
        qty = random.randint(1, 5)
        discount = round(random.choice([0.0, 0.0, 0.0, 0.5, 1.0, 1.5, 2.0]), 2)
        unit_price = prod["price"]
        line_total = round(qty * unit_price - discount, 2)
        total += line_total

        transaction_items.append({
            "item_id": f"ITEM-{item_id:06d}",
            "transaction_id": f"TXN-{txn_id:05d}",
            "product_id": prod["product_id"],
            "quantity": float(qty),
            "unit_price": unit_price,
            "discount": discount,
        })
        item_id += 1

    transactions.append({
        "transaction_id": f"TXN-{txn_id:05d}",
        "customer_id": customer["customer_id"],
        "store_id": store["store_id"],
        "transaction_date": txn_date.strftime("%Y-%m-%d %H:%M:%S"),
        "total_amount": round(total, 2),
        "payment_method": random.choice(PAYMENT_METHODS),
        "status": random.choices(["completed", "refunded", "pending"], weights=[90, 7, 3])[0],
    })

transactions_df = spark.createDataFrame(transactions)
transactions_df.write.mode("overwrite").saveAsTable(f"{FULL_SCHEMA}.transactions")
print(f"  Wrote {transactions_df.count()} transactions")

transaction_items_df = spark.createDataFrame(transaction_items)
transaction_items_df.write.mode("overwrite").saveAsTable(f"{FULL_SCHEMA}.transaction_items")
print(f"  Wrote {transaction_items_df.count()} transaction items")

# ── 5. Payment History ──────────────────────────────────────────────
print("Generating payment history...")
payment_history = []
for pay_id in range(1, 401):
    customer = random.choice(customers)
    method = random.choice(PAYMENT_METHODS)
    card_last4 = str(random.randint(1000, 9999)) if method in ("credit_card", "debit_card") else None
    payment_history.append({
        "payment_id": f"PAY-{pay_id:04d}",
        "customer_id": customer["customer_id"],
        "payment_method": method,
        "card_last4": card_last4,
        "billing_address": f"{customer['state']}{customer['city']}{random.choice(STREETS)}{random.randint(1,30)}-{random.randint(1,20)}-{random.randint(1,15)}",
        "created_date": (datetime(2024, 1, 1) + timedelta(days=random.randint(0, 440))).strftime("%Y-%m-%d"),
    })

payment_history_df = spark.createDataFrame(payment_history)
payment_history_df.write.mode("overwrite").saveAsTable(f"{FULL_SCHEMA}.payment_history")
print(f"  Wrote {payment_history_df.count()} payment records")

print("\nAll tables created successfully in", FULL_SCHEMA)
