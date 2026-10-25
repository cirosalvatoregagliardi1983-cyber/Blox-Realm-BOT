import io
import json
import os
import requests
import discord
from discord import app_commands
from discord.ext import commands
from PIL import Image, ImageDraw, ImageFont

# --- CONFIGURAZIONE E SALVATAGGIO DATI ---
DATA_FILE = "economy_data.json"

def load_data():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r") as f:
            return json.load(f)
    return {"users": {}, "items": {}}

def save_data(data):
    with open(DATA_FILE, "w") as f:
        json.dump(data, f, indent=4)

data = load_data()

def get_user_balance(user_id: str) -> int:
    uid = str(user_id)
    if uid not in data["users"]:
        data["users"][uid] = {"balance": 1000, "inventory": []}
        save_data(data)
    return data["users"][uid]["balance"]

def add_user_item(user_id: str, item_name: str):
    uid = str(user_id)
    if uid not in data["users"]:
        data["users"][uid] = {"balance": 1000, "inventory": []}
    data["users"][uid]["inventory"].append(item_name)
    save_data(data)

# --- INIZIALIZZAZIONE BOT ---
intents = discord.Intents.default()
intents.guilds = True
intents.messages = True

class BloxRealmBot(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix="!", intents=intents)

    async def setup_hook(self):
        await self.tree.sync()
        print("Comandi slash sincronizzati con successo.")

bot = BloxRealmBot()

# --- MESSAGGIO GUIDA IN DM ALL'INVITO ---
@bot.event
async def on_guild_join(guild: discord.Guild):
    async for entry in guild.audit_logs(limit=5, action=discord.AuditLogAction.BOT_ADD):
        if entry.target.id == bot.user.id:
            inviter = entry.user
            embed_dm = discord.Embed(
                title="🚀 Benvenuto nell'Ecosistema Blox Realm!",
                description=(
                    "Grazie per aver aggiunto il bot al tuo server!\n\n"
                    "**Guida Rapida ai Comandi:**\n"
                    "• `/crea-oggetto`: Crea nuovi articoli da mettere in vendita nel tuo stand.\n"
                    "• `/setup`: Genera lo stand interattivo con gli oggetti creati e i pulsanti di acquisto.\n"
                    "• `/bilancio`: Controlla il tuo saldo attuale.\n"
                    "• `/inventario`: Genera la grafica con tutti gli oggetti in tuo possesso.\n"
                    "• `/trade`: Avvia una proposta di scambio di un oggetto con un altro utente."
                ),
                color=0x7b2cbf
            )
            try:
                await inviter.send(embed=embed_dm)
            except Exception as e:
                print(f"Impossibile inviare DM all'utente: {e}")
            break

# --- VISTA E PULSANTI PER LO STAND DEGLI OGGETTI ---
class BuyButton(discord.ui.Button):
    def __init__(self, item_name: str, price: int):
        super().__init__(
            label=f"Acquista ({price} 🪙)",
            style=discord.ButtonStyle.success,
            custom_id=f"buy_{item_name}"
        )
        self.item_name = item_name
        self.price = price

    async def callback(self, interaction: discord.Interaction):
        user_id = str(interaction.user.id)
        current_bal = get_user_balance(user_id)

        if current_bal < self.price:
            await interaction.response.send_message(
                f"❌ Non hai abbastanza fondi! Ti servono {self.price} 🪙 (Saldo attuale: {current_bal} 🪙).",
                ephemeral=True
            )
            return

        # Sottrai saldo e aggiungi oggetto all'inventario
        data["users"][user_id]["balance"] -= self.price
        add_user_item(user_id, self.item_name)

        await interaction.response.send_message(
            f"✅ **{self.item_name}** aggiunto al tuo inventario!",
            ephemeral=True
        )

# --- VISTA PER IL TRADE INTERATTIVO ---
class TradeView(discord.ui.View):
    def __init__(self, sender: discord.Member, receiver: discord.Member, item_name: str):
        super().__init__(timeout=120)
        self.sender = sender
        self.receiver = receiver
        self.item_name = item_name

    @discord.ui.button(label="Accetta Scambio", style=discord.ButtonStyle.success)
    async def accept(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.receiver.id:
            await interaction.response.send_message("❌ Solo il destinatario può accettare lo scambio.", ephemeral=True)
            return

        sender_id = str(self.sender.id)
        receiver_id = str(self.receiver.id)

        # Sposta l'oggetto dal mittente al destinatario
        if self.item_name in data["users"][sender_id]["inventory"]:
            data["users"][sender_id]["inventory"].remove(self.item_name)
            add_user_item(receiver_id, self.item_name)
            
            for item in self.children:
                item.disabled = True

            await interaction.response.edit_message(
                content=f"🤝 **Scambio Concluso!** {self.sender.mention} ha trasferito **{self.item_name}** a {self.receiver.mention}.",
                view=self
            )
        else:
            await interaction.response.send_message("❌ Lo scambio è fallito: l'oggetto non è più presente nell'inventario del mittente.", ephemeral=True)

    @discord.ui.button(label="Rifiuta", style=discord.ButtonStyle.danger)
    async def decline(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.receiver.id and interaction.user.id != self.sender.id:
            await interaction.response.send_message("❌ Non sei autorizzato a gestire questo scambio.", ephemeral=True)
            return

        for item in self.children:
            item.disabled = True

        await interaction.response.edit_message(
            content=f"❌ **Scambio Annullato.**",
            view=self
        )

# --- COMANDI SLASH ---

@bot.tree.command(name="crea-oggetto", description="Crea un nuovo oggetto da mettere in vendita nel tuo stand.")
@app_commands.describe(
    nome="Nome dell'oggetto",
    descrizione="Breve descrizione dell'oggetto",
    prezzo="Prezzo di vendita in crediti",
    url_immagine="Link diretto all'immagine dell'oggetto"
)
async def crea_oggetto(interaction: discord.Interaction, nome: str, descrizione: str, prezzo: int, url_immagine: str):
    data["items"][nome] = {
        "description": descrizione,
        "price": prezzo,
        "image_url": url_immagine,
        "creator": interaction.user.display_name
    }
    save_data(data)

    await interaction.response.send_message(
        f"🎨 Oggetto **{nome}** creato con successo! Ora puoi usarlo con il comando `/setup`.",
        ephemeral=True
    )

@bot.tree.command(name="setup", description="Mostra lo stand con tutti gli oggetti creati e i pulsanti d'acquisto.")
async def setup(interaction: discord.Interaction):
    if not data["items"]:
        await interaction.response.send_message(
            "⚠️ Nessun oggetto trovato! Crea prima un oggetto usando il comando `/crea-oggetto`.",
            ephemeral=True
        )
        return

    await interaction.response.defer()

    # Creazione della vetrina con Embed e pulsanti
    for item_name, item_info in data["items"].items():
        embed = discord.Embed(
            title=f"🏷️ {item_name.upper()}",
            description=item_info["description"],
            color=0x111111
        )
        embed.add_field(name="Prezzo", value=f"{item_info['price']} 🪙", inline=True)
        embed.set_thumbnail(url=item_info["image_url"])

        view = discord.ui.View()
        view.add_item(BuyButton(item_name, item_info["price"]))

        await interaction.channel.send(embed=embed, view=view)

    await interaction.followup.send("🛍️ **Stand configurato e pubblicato con successo!**", ephemeral=True)

@bot.tree.command(name="bilancio", description="Controlla quanti soldi possiedi attualmente.")
async def bilancio(interaction: discord.Interaction):
    bal = get_user_balance(interaction.user.id)
    embed = discord.Embed(
        title="💰 Bilancio Personale",
        description=f"Hai a disposizione: **{bal} 🪙**",
        color=0xf1c40f
    )
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="inventario", description="Genera una grafica personalizzata con gli oggetti che hai comprato.")
async def inventario(interaction: discord.Interaction):
    await interaction.response.defer()

    user_id = str(interaction.user.id)
    user_inventory = data["users"].get(user_id, {}).get("inventory", [])

    if not user_inventory:
        await interaction.followup.send("🎒 Il tuo inventario è vuoto! Acquista degli oggetti dallo stand.", ephemeral=True)
        return

    # Generazione Immagine Inventario con Pillow
    width, height = 800, 600
    base_img = Image.new("RGB", (width, height), "#1a1a1a")
    draw = ImageDraw.Draw(base_img)

    try:
        font_title = ImageFont.truetype("arial.ttf", 32)
        font_item = ImageFont.truetype("arial.ttf", 20)
    except:
        font_title = font_item = ImageFont.load_default()

    draw.text((30, 30), f"INVENTARIO DI {interaction.user.display_name.upper()}", fill="#ffffff", font=font_title)

    x_offset, y_offset = 30, 100
    box_size = 120

    for item_name in user_inventory:
        item_info = data["items"].get(item_name)
        
        # Disegna il box dell'oggetto
        draw.rectangle([(x_offset, y_offset), (x_offset + box_size, y_offset + box_size)], fill="#2d2d2d", outline="#7b2cbf", width=2)
        
        # Tenta di scaricare e posizionare la miniatura
        if item_info and "image_url" in item_info:
            try:
                res = requests.get(item_info["image_url"], timeout=5)
                img_obj = Image.open(io.BytesIO(res.content)).convert("RGBA")
                img_obj = img_obj.resize((80, 80))
                base_img.paste(img_obj, (x_offset + 20, y_offset + 10), img_obj)
            except Exception as e:
                print(f"Errore caricamento icona inventario: {e}")

        # Nome oggetto sotto il box
        draw.text((x_offset, y_offset + 95), item_name[:12], fill="#ffffff", font=font_item)

        x_offset += 150
        if x_offset > width - box_size:
            x_offset = 30
            y_offset += 140

    # Salva e invia l'immagine come file
    img_bytes = io.BytesIO()
    base_img.save(img_bytes, format="PNG")
    img_bytes.seek(0)

    file_discord = discord.File(fp=img_bytes, filename="inventario.png")
    await interaction.followup.send(file=file_discord)

@bot.tree.command(name="trade", description="Crea una proposta di scambio con un altro utente.")
@app_commands.describe(
    destinatario="L'utente con cui vuoi scambiare",
    oggetto="L'oggetto del tuo inventario che vuoi offrire"
)
async def trade(interaction: discord.Interaction, destinatario: discord.Member, oggetto: str):
    user_id = str(interaction.user.id)
    user_inventory = data["users"].get(user_id, {}).get("inventory", [])

    if oggetto not in user_inventory:
        await interaction.response.send_message(f"❌ Non possiedi l'oggetto **{oggetto}** nel tuo inventario!", ephemeral=True)
        return

    embed = discord.Embed(
        title="🔄 PROPOSTA DI SCAMBIO",
        description=(
            f"{interaction.user.mention} vuole scambiare l'oggetto **{oggetto}** con {destinatario.mention}.\n\n"
            f"Accetti lo scambio?"
        ),
        color=0x3498db
    )

    view = TradeView(sender=interaction.user, receiver=destinatario, item_name=oggetto)
    await interaction.response.send_message(content=destinatario.mention, embed=embed, view=view)

# --- AVVIO BOT ---
bot.run("MTU2Mzg0OTQwMDg0ODIyNDI1Ng.GJGYEP.kR3yvtp_Y55cOI85dIM_s5jNIOCXP1hYxodTCc")
