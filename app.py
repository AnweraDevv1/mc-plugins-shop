import os, json, threading
from flask import Flask, render_template, jsonify, request
from flask_sqlalchemy import SQLAlchemy
from flask_cors import CORS
import telebot
from telebot import types
from models import db, Product, Purchase
from config import BOT_TOKEN, ADMIN_USERNAME, WEBAPP_URL, SECRET_KEY, DATABASE_URL, PORT

app = Flask(__name__)
app.config['SECRET_KEY'] = SECRET_KEY
app.config['SQLALCHEMY_DATABASE_URI'] = DATABASE_URL
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
CORS(app)
db.init_app(app)
bot = telebot.TeleBot(BOT_TOKEN)

# ==================== BOT ====================
@bot.message_handler(commands=['start'])
def start_cmd(msg):
    markup = types.InlineKeyboardMarkup(row_width=1)
    markup.add(types.InlineKeyboardButton(
        text="🎮 Открыть Магазин Плагинов",
        web_app=types.WebAppInfo(url=WEBAPP_URL)
    ))
    bot.send_message(msg.chat.id,
        f"👋 Привет, {msg.from_user.first_name}!\n\n"
        "🏪 **Магазин Плагинов для Minecraft**\n\n"
        "🔹 Лучшие плагины для вашего сервера\n"
        "🔹 Быстрая доставка\n"
        "🔹 Поддержка 24/7\n\n"
        "Нажми кнопку ниже чтобы открыть магазин 👇",
        parse_mode='Markdown', reply_markup=markup)

@bot.message_handler(commands=['admin'])
def admin_cmd(msg):
    if msg.from_user.username and msg.from_user.username.lower() == ADMIN_USERNAME.lower():
        markup = types.InlineKeyboardMarkup(row_width=1)
        markup.add(types.InlineKeyboardButton(
            text="⚙️ Панель Администратора",
            web_app=types.WebAppInfo(url=f"{WEBAPP_URL}/admin")
        ))
        bot.send_message(msg.chat.id, "🔐 **Панель администратора**", parse_mode='Markdown', reply_markup=markup)
    else:
        bot.send_message(msg.chat.id, "⛔ Нет доступа.")

# ==================== API ====================
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/admin')
def admin_page():
    return render_template('admin.html')

@app.route('/api/products', methods=['GET'])
def get_products():
    cat = request.args.get('category')
    q = Product.query.filter_by(is_active=True)
    if cat and cat != 'all':
        q = q.filter_by(category=cat)
    return jsonify([p.to_dict() for p in q.order_by(Product.created_at.desc()).all()])

@app.route('/api/products/<int:pid>', methods=['GET'])
def get_product(pid):
    return jsonify(Product.query.get_or_404(pid).to_dict())

@app.route('/api/products', methods=['POST'])
def create_product():
    d = request.json
    p = Product(name=d['name'], description=d['description'], price=float(d['price']),
                image_url=d.get('image_url',''), category=d.get('category','Плагины'),
                version=d.get('version','1.20+'))
    db.session.add(p)
    db.session.commit()
    return jsonify(p.to_dict()), 201

@app.route('/api/products/<int:pid>', methods=['PUT'])
def update_product(pid):
    p = Product.query.get_or_404(pid)
    d = request.json
    for k in ['name','description','price','image_url','category','version','is_active']:
        if k in d:
            setattr(p, k, float(d[k]) if k=='price' else d[k])
    db.session.commit()
    return jsonify(p.to_dict())

@app.route('/api/products/<int:pid>', methods=['DELETE'])
def delete_product(pid):
    p = Product.query.get_or_404(pid)
    p.is_active = False
    db.session.commit()
    return jsonify({'ok': True})

@app.route('/api/purchase', methods=['POST'])
def make_purchase():
    d = request.json
    p = Product.query.get_or_404(d['product_id'])
    ui = d['user_info']
    pur = Purchase(product_id=p.id, user_id=ui.get('user_id',0),
                   username=ui.get('username',''), first_name=ui.get('first_name',''))
    p.purchases_count += 1
    db.session.add(pur)
    db.session.commit()
    try:
        text = (f"🛒 **Новая покупка!**\n\n📦 {p.name}\n💰 {p.price:.0f}₽\n"
                f"👤 @{ui.get('username','N/A')} | {ui.get('first_name','N/A')}\n🆔 ID: {ui.get('user_id','N/A')}")
        # Send to admin - find chat by trying to send
        admin_chats = db.session.execute(db.text("SELECT DISTINCT user_id FROM purchases WHERE username = 'rev1lss'")).fetchall()
        for row in admin_chats:
            try: bot.send_message(row[0], text, parse_mode='Markdown')
            except: pass
    except: pass
    return jsonify({'ok': True, 'purchase_id': pur.id, 'admin_username': ADMIN_USERNAME})

@app.route('/api/purchases', methods=['GET'])
def get_purchases():
    return jsonify([{'id':p.id,'product_name':p.product.name,'product_price':p.product.price,
                     'username':p.username,'first_name':p.first_name,'status':p.status,
                     'created_at':p.created_at.isoformat()} for p in Purchase.query.order_by(Purchase.created_at.desc()).limit(50).all()])

@app.route('/api/stats', methods=['GET'])
def get_stats():
    return jsonify({'total_products': Product.query.filter_by(is_active=True).count(),
                    'total_purchases': Purchase.query.count(),
                    'total_revenue': db.session.query(db.func.sum(Product.price)).join(Purchase).scalar() or 0})

@app.route('/api/categories', methods=['GET'])
def get_categories():
    return jsonify([c[0] for c in db.session.query(Product.category).distinct().all() if c[0]])

def seed():
    if Product.query.count() == 0:
        for p in [
            {'name':'EssentialsX Pro','description':'Мощный набор команд: телепортация, дома, экономику и др.','price':299,'image_url':'https://img.icons8.com/color/200/minecraft-pickaxe.png','category':'Команды','version':'1.16-1.21'},
            {'name':'WorldGuard Ultra','description':'Защита территорий, регионы, флаги, анти-грифер.','price':499,'image_url':'https://img.icons8.com/color/200/shield.png','category':'Защита','version':'1.18-1.21'},
            {'name':'CustomEnchants+','description':'100+ уникальных зачарований: огненные мечи, ледяные луки.','price':599,'image_url':'https://img.icons8.com/color/200/magic-wand.png','category':'Геймплей','version':'1.17-1.21'},
            {'name':'EconomyMaster','description':'Полная экономика: магазины, аукционы, банки, работа.','price':399,'image_url':'https://img.icons8.com/color/200/money-bag.png','category':'Экономика','version':'1.16-1.21'},
            {'name':'MobArena Elite','description':'Арена с волнами мобов, боссы, лут, классы.','price':349,'image_url':'https://img.icons8.com/color/200/sword.png','category':'Мини-игры','version':'1.18-1.21'},
            {'name':'SkyBlock Ultimate','description':'Полный SkyBlock: острова, задания, прокачка.','price':799,'image_url':'https://img.icons8.com/color/200/island.png','category':'Сборки','version':'1.19-1.21'},
            {'name':'LuckPerms VIP','description':'Система прав и рангов, группы, наследование.','price':199,'image_url':'https://img.icons8.com/color/200/user-shield.png','category':'Управление','version':'1.14-1.21'},
            {'name':'Dynmap RealTime','description':'Интерактивная карта сервера в браузере.','price':249,'image_url':'https://img.icons8.com/color/200/map.png','category':'Утилиты','version':'1.16-1.21'},
        ]:
            db.session.add(Product(**p))
        db.session.commit()
        print("✅ Seeded 8 products")

def run_bot():
    print("🤖 Bot polling started")
    bot.infinity_polling()

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
        seed()
    threading.Thread(target=run_bot, daemon=True).start()
    app.run(host='0.0.0.0', port=PORT, debug=False)
