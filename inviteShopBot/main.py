import discord
from datetime import datetime, timezone
from discord.ext import commands
from discord.ui import Button, View
import aiosqlite

from discord import Embed

token = "MTM0MzM4MjQ5ODkxODQwNDIyNg.GeyYtG.lJ_lPBPNvxfZuZIV5ffaKsUdjoXEzMGsZ9WT1Y"

admin = ['luke3858481', 'thedapperlad']

invites = []
embed = None
msg = None
intents = discord.Intents.all()
bot = commands.Bot(command_prefix='/', intents=intents)

INVITE_FILE = 'main/invites.txt'


@bot.event
async def on_ready():
    print(f'We have logged in as {bot.user}')
    async with aiosqlite.connect("user_invites.db") as db:
        async with db.cursor() as cursor:
            await cursor.execute('CREATE TABLE IF NOT EXISTS users (row_id INTEGER PRIMARY KEY AUTOINCREMENT, id INTEGER, invites INTEGER, guild INTEGER, UNIQUE (id, guild))')
        await db.commit()
        
        
        async with db.cursor() as cursor:
            for guild in bot.guilds:
                try:
                    # Fetch all invites for the guild
                    invites = await guild.invites()

                    for invite in invites:
                        user = invite.inviter.id  #userid for the inviter. be careful, one user can have multiple invite links
                        invite_count = invite.uses  #number of uses for this individual invite. 
                        guild_id = guild.id  #current guild id
                        print(invite)

                        await cursor.execute("""
                            INSERT INTO users (id, invites, guild)
                            VALUES (?, ?, ?)
                            ON CONFLICT(id, guild) DO UPDATE SET
                                invites = invites + EXCLUDED.invites
                        """, (user, invite_count, guild_id))
                    await db.commit()
                    
                except Exception as e:
                    print(f"Error processing invites for guild {guild.name}: {e}")


@bot.command()
async def adduser(ctx):
     async with aiosqlite.connect("user_invites.db") as db:
        async with db.cursor() as cursor:
            await cursor.execute('SELECT id FROM users WHERE guild = ?', (ctx.guild.id))
            data = await cursor.fetchone()
            if data: 
                await cursor.execute('UPDATE users SET id = ? WHERE guild = ?', (member.id, ctx.guild.id,))
            else:
                pass
        await db.commit


@bot.event
async def on_guild_join(guild):
    print('joined new guild')
    channel = next((channel for channel in guild.text_channels if channel.permissions_for(guild.me).send_messages), None)
    if channel:
        await channel.send('Hello! If you\'d like to get started, please type \'/setshop\' in the appropriate channel.')
    else:
        print("No suitable text channel found to send the message.")
        
@bot.event
async def on_member_join(member): #DELETE MOST OF THIS. NEW STRAT: ITERATE THROUGH ALL GUILD INVITES, COMBINE THE NUMBERS FOR USERS WITH MULTIPLE INVITE CODES. THEN, ITERATE THROUGH ALL THE IDS IN SQLITE TABLE AND SEE WHICH INVITE COUNT IS TOO LOW (that means thats the new invite). GIVE THE PROPER GUY CURRENCY  ACCORDINGLY
    global invites
    
    if invites == None:
        print('No user has invited another during this session. No invite tokens awarded.')
        return
    #use new_member to verfiy its a legit invite
   
    total_invites = await member.guild.invites()
    user = None
    
    for invite in list(invites):
        if invite.expires_at < datetime.now(timezone.utc):
            del invites[invite]
        if invite not in t_invite:
            del invites[invite]
        for t_invite in total_invites:
            if invite.code == t_invite.code:
                if invite.uses < t_invite.uses:
                    user = invite.inviter
                    invites[invite] = t_invite
                    break
    
    if user != None:
        print(user)
    else: 
        print('no valid user found')
    
    
@bot.event
async def on_invite_create(invite):
    global invites
    
    invites.append(invite)
    
    async with aiosqlite.connect("user_invites.db") as db:
        async with db.cursor() as cursor:
            user = invite.inviter.id  #userid for the inviter. be careful, one user can have multiple invite links
            invite_count = invite.uses  #number of uses for this individual invite. 
            guild_id = invite.guild.id  #current guild id
            await cursor.execute("""
                INSERT INTO users (id, invites, guild)
                VALUES (?, ?, ?)
                ON CONFLICT(id, guild) DO UPDATE SET
                    invites = invites + EXCLUDED.invites
            """, (user, invite_count, guild_id))
        await db.commit()


    
@bot.command()
async def setshop(ctx):
    print('Shop has been set.')
    global embed
    global msg
    embed = Embed(
        color=discord.Color.dark_blue(),
        title='fart',
        )
    
    button1 = PurchaseButton(style=discord.ButtonStyle.blurple, emoji='1️⃣', purchase_value=1)
    button2 = PurchaseButton(style=discord.ButtonStyle.blurple, emoji='2️⃣', purchase_value=2)
    button3 = PurchaseButton(style=discord.ButtonStyle.blurple, emoji='3️⃣', purchase_value=3)
    button4 = PurchaseButton(style=discord.ButtonStyle.blurple, emoji='4️⃣', purchase_value=4)
    button5 = PurchaseButton(style=discord.ButtonStyle.blurple, emoji='5️⃣', purchase_value=5)
    
    view = View()
    view.add_item(button1)
    view.add_item(button2)
    view.add_item(button3)
    view.add_item(button4)
    view.add_item(button5)

    msg = await ctx.channel.send(embed=embed, view=view)
    

class PurchaseButton(Button):
    global purchase_value
    
    def __init__(self, style, emoji, purchase_value):
        super().__init__(style=style,emoji=emoji)
        self.purchase_value = purchase_value
    
    async def callback(self, interaction):
        print(f'value={self.purchase_value}')
        
        view =  View()
        confirm_button = ConfirmButton()
        deny_button = DenyButton()
        view.add_item(confirm_button)
        view.add_item(deny_button)
        await interaction.response.send_message(f"You are trying to purchase ___ for ___. Are you sure you want to do this?", view=view, ephemeral=True)

class ConfirmButton(Button):
    def __init__(self):
        super().__init__(style=discord.ButtonStyle.green, emoji='✅')
    async def callback(self, interaction):
        await interaction.response.send_message("Purchase successful!", ephemeral=True)
class DenyButton(Button):
    def __init__(self):
        super().__init__(style=discord.ButtonStyle.red, emoji='❌')
    async def callback(self, interaction):
        await interaction.response.send_message("Purchase cancelled.", ephemeral=True)

    
@bot.command()
async def insertitem(ctx):
    await insert_shop_item(ctx)

async def insert_shop_item(ctx):
    global embed
    embed.add_field(name="Test item", value="Description of test item", inline=False)
    
    await msg.edit(embed=embed)
    


bot.run(token)