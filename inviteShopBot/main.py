import discord
from datetime import datetime, timezone
from discord.ext import commands, tasks
from discord.ui import Button, View, Select
import aiosqlite

from collections import defaultdict
from discord import app_commands
import json

from discord import Embed

token = "token here"

admin = [] #user ids of the admins that are allowed to interact with bot. do /admin to add new admins to json file.
multiplier = 100 #edit this to edit how many coins a user recieves per invite. 
heart_beat = 300 #edit this to edit how often the bot checks to see if invites expired (in seconds)

subscription_plans = {}
embed = None
msg = None

intents = discord.Intents.all()
bot = commands.Bot(command_prefix='/', intents=intents)


@bot.event
async def on_ready():
    print("Registered commands:")
    for command in bot.tree.get_commands():
        print(command.name)

    await bot.tree.sync()
    await setup_admins_table()

    print(f'We have logged in as {bot.user}')
    async with aiosqlite.connect("users.db") as db:
        async with db.cursor() as cursor:
            await cursor.execute('CREATE TABLE IF NOT EXISTS shoppers (row_id INTEGER PRIMARY KEY AUTOINCREMENT, id INTEGER, name STRING, invites INTEGER, guild INTEGER, coins INTEGER, UNIQUE (id, guild))')
        await db.commit()
        
        
        async with db.cursor() as cursor:
            for guild in bot.guilds:
                try:
                    members = guild.members
                    guild_id = guild.id
                    for member in members:
                        user_id = member.id
                        #setup table
                        await cursor.execute("""
                            INSERT INTO shoppers (id, name, invites, guild, coins)
                            VALUES (?, ?, 0, ?, 0)
                            ON CONFLICT(id, guild) DO NOTHING
                        """, (user_id, member.name, guild_id))
                        
                    invites = await guild.invites()
                    for invite in invites:
                        user = invite.inviter.id  #userid for the inviter. be careful, one user can have multiple invite links
                        invite_count = invite.uses  #number of uses for this individual invite
                        print(invite)

                        await cursor.execute("""
                            INSERT INTO shoppers (id, name, invites, guild, coins)
                            VALUES (?, ?, ?, ?, 0)
                            ON CONFLICT(id, guild) DO UPDATE SET
                                invites = invites + EXCLUDED.invites
                        """, (user, invite.inviter.name, invite_count, guild_id))
                    await db.commit()
                    await update_shop(False, guild_id=guild_id)
                    
                except Exception as e:
                    print(f"Error processing invites for guild {guild.name}: {e}")
                    for channel in guild.text_channels:
                        if channel.permissions_for(guild.me).send_messages:
                            await channel.send("I need invite permissions to track invites properly! Bot will not work properly otherwise, give it `Manage Server` permissions. Call `/setshop` when done.")
                            break 
    refresh_invites.start()
@bot.event
async def on_resumed():
    for guild in bot.guilds:
        update_shop(False, guild_id=guild.id)
    
@bot.event
async def on_guild_join(guild):
    print('joined new guild')
    channel = next((channel for channel in guild.text_channels if channel.permissions_for(guild.me).send_messages), None)
    if channel:
        await channel.send('Hello! If you\'d like to get started, please type `/setshop` in the appropriate channel.')
    else:
        print(f"Failed to find channel to send msg in {guild.name}")
    
    async with aiosqlite.connect("users.db") as db:
        async with db.cursor() as cursor:
            for member in guild.members:
                if member.bot:
                    continue  
                await cursor.execute("SELECT id FROM shoppers WHERE id = ? AND guild = ?", (member.id, guild.id))
                result = await cursor.fetchone()

                if result is None:
                    print(f"Adding {member.name} ({member.id}) to the database.")
                    await cursor.execute("""
                        INSERT INTO shoppers (id, name, invites, guild, coins)
                        VALUES (?, ?, 0, ?, 0)
                    """, (member.id, member.name, guild.id))
        await db.commit()
            
@bot.event
async def on_member_join(member): 
    guild = member.guild
    guild_id = guild.id
    invites = await guild.invites()
    inviteTracking = {}
    user = None
    new_member = False
    row_id = None  
    
    for invite in invites:
        inviteTracking[invite.inviter.id] = inviteTracking.get(invite.inviter.id, 0) + invite.uses
    print(inviteTracking)
    
    async with aiosqlite.connect("users.db") as db:
        async with db.cursor() as cursor:
            await cursor.execute("SELECT id, invites FROM shoppers WHERE guild = ?", (guild_id,))
            db_users = await cursor.fetchall()
            
            for user_id, db_invites in db_users:
                if user_id in inviteTracking:
                    new_invites = inviteTracking[user_id]
                    if db_invites < new_invites:
                        print(f"User {user_id} has fewer invites in DB ({db_invites}) than in the new data ({new_invites})")
                        user = user_id  # this is the inviter
                        await cursor.execute("""
                            UPDATE shoppers
                            SET invites = ?
                            WHERE id = ? AND guild = ?
                        """, (new_invites, user_id, guild_id))
                        
            await cursor.execute("SELECT rowid FROM shoppers WHERE id = ? AND guild = ?", (member.id, guild_id))
            db_member = await cursor.fetchone()
            
            if db_member is None: 
                new_member = True
                print(f"Adding new user {member.id} to the database")
                
                await cursor.execute("""
                    INSERT INTO shoppers (id, name, invites, guild, coins)
                    VALUES (?, ?, 0, ?, 0)
                """, (member.id, member.name, guild_id))

                await cursor.execute("SELECT last_insert_rowid()")
                row_id = (await cursor.fetchone())[0]
                print(f"New row_id for {member.id} is {row_id}")
                    
            await db.commit()

    if user is not None and new_member:
        print(f"{user} gained currency")
        coins = 1 * multiplier
        async with aiosqlite.connect("users.db") as db:
            async with db.cursor() as cursor:
                await cursor.execute("""
                    UPDATE shoppers
                    SET coins = coins + ?
                    WHERE id = ? AND guild = ?
                """, (coins, user, guild_id,))
            await db.commit()
    else: 
        print('No valid user found')
        

@tasks.loop(seconds=heart_beat) 
async def refresh_invites():
    for guild in bot.guilds:
        await update_invites(guild)
        print(f"Invites automatically updated for {guild}")
        
@bot.event
async def on_invite_delete(invite): #probably wont need this, but just in case there are some stinkers deleting invites
    async with aiosqlite.connect("users.db") as db:
        async with db.cursor() as cursor:
            guild_id = invite.guild.id
            
            await cursor.execute("""
                SELECT id FROM shoppers WHERE guild = ? AND id = (SELECT id FROM shoppers WHERE invites = (SELECT MAX(invites) FROM shoppers WHERE guild = ?))
            """, (guild_id, guild_id))
            row = await cursor.fetchone()

            if row:
                user_id = row[0]
                await cursor.execute("""
                    UPDATE shoppers SET invites = 0 WHERE id = ? AND guild = ?
                """, (user_id, guild_id))
                await db.commit()

                
async def update_invites(guild):
    async with aiosqlite.connect("users.db") as db:
        async with db.cursor() as cursor:
            try:
                invites = await guild.invites()
                current_invites = {invite.inviter.id: invite.uses for invite in invites}

                for user_id, invite_count in current_invites.items():
                    await cursor.execute("""
                        INSERT INTO shoppers (id, name, invites, guild, coins)
                        VALUES (?, ?, ?, ?, 0)
                        ON CONFLICT(id, guild) DO UPDATE SET invites = ?
                    """, (user_id, str(user_id), invite_count, guild.id, invite_count))

                #checks for expired invites
                await cursor.execute("SELECT id, invites FROM shoppers WHERE guild = ?", (guild.id,))
                all_users = await cursor.fetchall()

                for user_id, stored_invites in all_users:
                    if user_id not in current_invites:
                        await cursor.execute("""
                            UPDATE shoppers SET invites = 0 WHERE id = ? AND guild = ?
                        """, (user_id, guild.id))

                await db.commit()

            except discord.Forbidden:
                print(f"Missing invite permissions in {guild.name}")


@bot.event
async def on_invite_create(invite): #refreshes the table everytime a new invite is made
    await update_invites(invite.guild)

        
@bot.tree.command(name="setshop")
async def setshop(interaction:discord.Interaction):
    if interaction.user.id not in await get_admins(): 
        await interaction.response.send_message(f"This command is reserved for admins.", ephemeral=True)
        return
    try:
        await update_shop(True, interaction.guild_id, interaction=interaction)
        await interaction.response.send_message("Shop created", ephemeral=True)
        print('Shop has been set.')
    except Exception as e:
        await interaction.response.send_message("Failed to create shop. Make sure the bot has proper perms.", ephemeral=True)
        print(f'Error setting shop: {e}')

SHOP_MESSAGE_FILE = "shop_messages.json"
async def save_shop_message(guild_id, channel_id, message_id):
    try:
        with open(SHOP_MESSAGE_FILE, "r") as f:
            data = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        data = {}
    data[str(guild_id)] = {"channel_id": channel_id, "message_id": message_id}

    with open(SHOP_MESSAGE_FILE, "w") as f:
        json.dump(data, f, indent=4)
        
async def get_all_shop_messages():
    """Retrieve all saved shop messages for all guilds."""
    try:
        with open(SHOP_MESSAGE_FILE, "r") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}  

async def update_shop(new: bool, guild_id: int, interaction:discord.Interaction=None):
    db_name = f"shop_{guild_id}.db"
    
    global embed
    embed = Embed(
        color=discord.Color.dark_blue(),
        title='💰 Welcome to the `Invite Shop` 💰',
        description="Click on a category to see available items! Check your balance with the 🪙 button.\nConfused? Click on the 📝!"
    )

    async with aiosqlite.connect(db_name) as db:
        async with db.execute("SELECT name FROM sqlite_master WHERE type='table';") as cursor:
            tables = await cursor.fetchall()

    category_buttons = []
    visible_count = 0 

    for table in tables:
        if visible_count >= 5:  
            break

        category = table[0]
        if category == "sqlite_sequence":
            continue

        async with aiosqlite.connect(db_name) as db:
            async with db.execute(f"SELECT * FROM {category} WHERE hidden = 0") as cursor:
                items = await cursor.fetchall()

        if not items:  # skip empty tables
            continue

        visible_count += 1 

        embed.add_field(name="", value="", inline=False)
        embed.add_field(name=f"\n`{visible_count}.` {category}!", value="", inline=False)

        item_grouped = {}

        for item in items:
            item_id, item_name, item_reward, item_cost, item_hidden = item

            if item_name not in item_grouped:
                item_grouped[item_name] = {
                    'cost': item_cost,
                    'stock': 0
                }

            item_grouped[item_name]['stock'] += 1

        for item_name, details in list(item_grouped.items()):
            embed.add_field(
                name=f"`{item_name}`🛒",
                value=f"\n> Cost: `{details['cost']}` 🪙\n> Stock: `{details['stock']}` ",
                inline=True
            )

        embed.add_field(name="", value=f"*Click `{visible_count}` to view more items in this category.*", inline=True)

        category_buttons.append(
            CategorySelect(style=discord.ButtonStyle.blurple, emoji=f"{visible_count}️⃣", category=category, value=visible_count, guild_id=guild_id)
        )

    guide_button = GuideButton()
    balance_button = BalanceButton()

    view = View()
    for button in category_buttons:
        view.add_item(button)

    view.add_item(guide_button)
    view.add_item(balance_button)

    shop_data = await get_all_shop_messages()

    if new:
        msg = await interaction.channel.send(embed=embed, view=view)
        await save_shop_message(guild_id, interaction.channel.id, msg.id)
        return

    if str(guild_id) not in shop_data:
        print(f"Guild ID {guild_id} is not associated with any active shop.")
        return

    data = shop_data[str(guild_id)]
    channel_id, message_id = data["channel_id"], data["message_id"]
    guild = bot.get_guild(int(guild_id))
    
    if not guild:
        print(f"Guild no longer exists. Call /setshop again.")
        return

    channel = bot.get_channel(channel_id)
    if not channel:
        print(f"Channel with shop no longer exists. Call /setshop again.")
        return
    try:
        msg = await channel.fetch_message(message_id)
        await msg.edit(embed=embed, view=view)
        print(f"Shop updated for guild {guild_id}.")
    except discord.Forbidden:
        print(f"Missing permissions to edit message {message_id} in guild {guild_id}.")


class PurchaseDropdown(Select):
    def __init__(self, items, category, guild_id):
        options = [
            discord.SelectOption(label=item_name, value=str(item_id), description=f"Cost: {details['cost']} 🪙 | Stock: {details['stock']}")
            for item_id, (item_name, details) in enumerate(items.items(), start=1)
        ]

        super().__init__(placeholder="Select an item to purchase...", min_values=1, max_values=1, options=options)
        self.items = items
        self.category = category
        self.guild_id = guild_id

    async def callback(self, interaction):
        selected_id = int(self.values[0])
        item_name = list(self.items.keys())[selected_id - 1]
        details = self.items[item_name]


        view =  View()
        confirm_button = ShopConfirmButton(self.category, details['item_id'], details['cost'], item_name, guild_id=self.guild_id)
        deny_button = DenyButton()
        view.add_item(confirm_button)
        view.add_item(deny_button)
        await interaction.response.send_message(f"You are trying to purchase {item_name} for {details['cost']}. Are you sure you want to do this?", view=view, ephemeral=True)


class CategorySelect(Button):
    def __init__(self, style, emoji, category, value, guild_id):
        super().__init__(style=style, emoji=emoji, custom_id=f"category_{value - 1}")
        self.category = category
        self.guild_id = guild_id

    async def callback(self, interaction):
        db_name = f"shop_{self.guild_id}.db"
        embed = discord.Embed(
            color=discord.Color.dark_blue(),
            title='`Available for Purchase`:',
            description=""
        )

        print(self.category)
        async with aiosqlite.connect(db_name) as db:
            try:
                async with db.execute(f"SELECT * FROM {self.category}") as cursor:
                    items = await cursor.fetchall()

                item_grouped = {}
                for item in items:
                    item_id, item_name, item_reward, item_cost, item_hidden = item
                    
                    if item_hidden == 1:
                        continue
                    
                    if item_name not in item_grouped:
                        item_grouped[item_name] = {
                            'cost': item_cost,
                            'stock': 0,
                            'item_id': item_id
                        }
                    
                    item_grouped[item_name]['stock'] += 1

                for count, (item_name, details) in enumerate(item_grouped.items(), start=1):
                    embed.add_field(
                        name=f" Item `{count}`: {item_name}    ",
                        value=f"Cost: `{details['cost']}` 🪙\nStock: {details['stock']} ",
                        inline=True
                    )

                view = View()
                view.add_item(PurchaseDropdown(item_grouped, self.category, self.guild_id))

                await interaction.response.send_message(f"Here are the items available for purchase in the `{self.category}` category:", embed=embed, view=view, ephemeral=True)

            except Exception as e:
                print(f"Error fetching items from category {self.category}: {e}")
                await interaction.response.send_message(f"An error occurred while fetching items from the category `{self.category}`.", ephemeral=True)


class ShopConfirmButton(Button):
    def __init__(self, category, line_id, item_cost, item_name, guild_id):
        super().__init__(style=discord.ButtonStyle.green, emoji='✅')
        self.category = category 
        self.line_id = line_id 
        self.item_cost = item_cost
        self.item_name = item_name
        self.guild_id = guild_id

    async def callback(self, interaction):
        db_name = f"shop_{self.guild_id}.db"
        user_id = interaction.user.id

        async with aiosqlite.connect('users.db') as db:
            async with db.execute("SELECT coins FROM shoppers WHERE id = ? AND guild = ?", (user_id, self.guild_id)) as cursor:
                result = await cursor.fetchone()
        if result is None:
            await interaction.response.send_message("You don't have an account yet. Try clicking the 📝 button on the shop to get started.", ephemeral=True)
            return

        user_balance = result[0]

        if user_balance < self.item_cost:
            await interaction.response.send_message("You don't have enough coins to buy this item. Click the 🪙 button on the shop to check your balance.", ephemeral=True)
            return

        async with aiosqlite.connect(db_name) as db:
            async with db.execute(f"SELECT item_reward FROM {self.category} WHERE id = ?", (self.line_id,)) as cursor:
                reward_result = await cursor.fetchone()

        if reward_result is None:
            await interaction.response.send_message("This item does not exist anymore.", ephemeral=True)
            return

        item_reward = reward_result[0] 

        new_balance = user_balance - self.item_cost
        async with aiosqlite.connect('users.db') as db:
            await db.execute("UPDATE shoppers SET coins = ? WHERE id = ? AND guild = ?", (new_balance, user_id, self.guild_id))
            await db.commit()

        try:
            await interaction.response.send_message("Purchase successful. Please check your DM's", ephemeral=True)
            await interaction.user.send(
                f"Purchase successful! You bought `{self.item_name}` for `{self.item_cost}` 🪙.\nYour Reward: `{item_reward}` 🎁.\nYour new balance is `{new_balance}` 🪙.\nIf you bought nitro, your nitro will be gifted by the shop owner shortly.")
            await self.log_purchase(interaction, item_reward)
        except discord.Forbidden:
            #in case user has dms disabled
            await interaction.response.send_message(
                "Purchase failed. Please allow 'Safe Direct Messaging' in your user settings.",
                ephemeral=True
            )
            new_balance = user_balance + self.item_cost #give money back
            async with aiosqlite.connect('users.db') as db:
                await db.execute("UPDATE shoppers SET coins = ? WHERE id = ? AND guild = ?", (new_balance, user_id, self.guild_id))
                await db.commit()
                return
        except discord.HTTPException as e:
            await interaction.response.send_message(
                f"Purchase failed. Please try again later.",
                ephemeral=True
            )
            new_balance = user_balance + self.item_cost #give money backl
            async with aiosqlite.connect('users.db') as db:
                await db.execute("UPDATE shoppers SET coins = ? WHERE id = ? AND guild = ?", (new_balance, user_id, self.guild_id))
                await db.commit()
                return
            return
        
        await delete_line(db_name, self.category, self.line_id, interaction.guild_id)
        
    async def log_purchase(self, interaction, item_reward):
        async with aiosqlite.connect("users.db") as db:
            async with db.cursor() as cursor:
                await cursor.execute("SELECT user_id FROM admins WHERE can_notify = 1")
                admins = await cursor.fetchall()

        channel = discord.utils.get(interaction.guild.text_channels, name="shop-logs")
        if channel:
            await channel.send(
                f"New purchase made by {interaction.user.name} ({interaction.user.id})\nItem: {self.item_name}\nReward: {item_reward}"
            )

        if self.category == '⚡NITRO⚡':
            if admins:
                for admin in admins:
                    admin_id = admin[0]
                    admin_user = await interaction.guild.fetch_member(admin_id)
                    if admin_user: 
                        try:
                            await admin_user.send(f"Nitro purchase made by {interaction.user.name} ({interaction.user.id}).\nItem: {self.item_name}\nReward: {item_reward}"
                            )
                        except discord.Forbidden:
                            pass  
            else:
                print(f"New Nitro purchase made by {interaction.user.name} ({interaction.user.id})")
                print(f"Item: {self.item_name}, Reward: {item_reward}")



class DenyButton(Button):
    def __init__(self):
        super().__init__(style=discord.ButtonStyle.red, emoji='✖️')
    async def callback(self, interaction):
        await interaction.response.send_message("Action cancelled.", ephemeral=True)
class TableConfirmButton(Button):
    def __init__(self, guild_id: int, category: str, line_id: int = None):
        super().__init__(style=discord.ButtonStyle.green, emoji='✅')
        self.guild_id = guild_id
        self.category = category
        self.line_id = line_id
        
    async def callback(self, interaction: discord.Interaction):
        db_name = f"shop_{self.guild_id}.db"

        if self.line_id is None:  # table delete
            await delete_table(db_name, self.category, self.guild_id)
            await interaction.response.send_message(f"🗑️ The table `{self.category}` has been deleted.", ephemeral=True)
        else:  # line delete
            await delete_line(db_name, self.category, self.line_id, self.guild_id)
            await interaction.response.send_message(f"🗑️ Line `{self.line_id}` has been deleted from `{self.category}`.", ephemeral=True)


class GuideButton(Button):
    def __init__(self):
        super().__init__(style=discord.ButtonStyle.gray, emoji='📝', custom_id="guide_button")
    async def callback(self, interaction):
        await interaction.response.send_message("**How does this bot work?**\nThis shop operates with `Invite Tokens`.\n\nYou gain these tokens by inviting new users to this server.\n\n**How do I invite people to the server?**\n-Click the dropdown next to the servers name in the top left.\n-Next, click `Invite People`.\n-Unfortunately, due to how discords API works there is a very small chance that your invite won't count. To be extra safe, click 'Edit Invite Link' and change some values.\n-Click any user on your friends list. \n-As soon as a new user accepts one of your invites, you will be automatically awarded with currency!\n\n**How do I see how much money I have?**\nClick the 🪙 button underneath the shop.\n\n**Where is my purchase?**\n-To maintain security, all purchase codes are sent to your DM's. If you didn't get a message, its likely you have set `Allow DM's from other server member` to false. Don't worry, you have been refunded.\n\n**My question isn't listed!**\n-Please message `thedapperlad` any further questions you have.", ephemeral=True)
class BalanceButton(Button):
    def __init__(self):
        super().__init__(style=discord.ButtonStyle.gray, emoji='🪙')
    
    async def callback(self, interaction):
        user_id = interaction.user.id  
        guild_id = interaction.guild.id 
        
        async with aiosqlite.connect("users.db") as db:
            async with db.cursor() as cursor:
                await cursor.execute("SELECT coins FROM shoppers WHERE id = ? AND guild = ?", (user_id, guild_id))
                result = await cursor.fetchone() 
                
        if result:
            coins = result[0] 
            await interaction.response.send_message(f"Your current balance is: 🪙 `{coins}`", ephemeral=True)
        else:
            await interaction.response.send_message("You don't have a balance yet.", ephemeral=True)


async def delete_table(db_name: str, category: str, guild_id:int):
    async with aiosqlite.connect(db_name) as db:
        async with db.cursor() as cursor:
            await cursor.execute(f"DROP TABLE {category}")
            await db.commit()
    await update_shop(False, guild_id=guild_id)

async def delete_line(db_name: str, category: str, line_id: int, guild_id:int):
    async with aiosqlite.connect(db_name) as db:
        async with db.cursor() as cursor:
            await cursor.execute(f"DELETE FROM {category} WHERE id = ?", (line_id,))
            await db.commit()
    await update_shop(False, guild_id=guild_id)

    
class GuildSelectView(View):
    def __init__(self, user, callback, *args):
        super().__init__(timeout=60)  
        self.user = user
        self.callback = callback  
        self.args = args #dynamic parameters!!? python is sick

        self.add_item(GuildDropdown(self))

class GuildDropdown(Select):
    def __init__(self, parent_view: GuildSelectView):
        self.parent_view = parent_view
        options = [
            discord.SelectOption(label=guild.name, value=str(guild.id))
            for guild in bot.guilds if self.parent_view.user in guild.members
        ]
        super().__init__(placeholder="Select a server...", options=options)

    async def callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.parent_view.user.id:
            await interaction.response.send_message("You can't use this selection.", ephemeral=True)
            return

        guild_id = int(self.values[0])  
        await self.parent_view.callback(interaction, guild_id, *self.parent_view.args) #this self.parent_view.callback is so cool. i wish c# had this

        

@bot.tree.command(name="insert", description="Add an item to a server's shop.")
async def insert(interaction: discord.Interaction, category: str, item_type: str, item_reward: str, cost: int, hidden: bool):
    if interaction.channel.type is not discord.ChannelType.private:
        await interaction.response.send_message("This command is reserved for private messages.", ephemeral=True)
        return
    if interaction.user.id not in await get_admins(): 
        await interaction.response.send_message("This command is reserved for admins.", ephemeral=True)
        return

    view = GuildSelectView(interaction.user, insert_item, category, item_type, item_reward, cost, hidden)
    await interaction.response.send_message("Select the server you want to add stock to:", view=view, ephemeral=True)

async def insert_item(interaction: discord.Interaction, guild_id: int, category: str, item_type: str, item_reward: str, cost: int, hidden: bool):
    db_name = f"shop_{guild_id}.db"
    hidden_bool = 1 if hidden else 0  # sqlite doesn't like booleans
    codes = [code.strip() for code in item_reward.split(',')]

    async with aiosqlite.connect(db_name) as db:
        async with db.cursor() as cursor:

            await cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name = ?", (category,))
            result = await cursor.fetchone()

            if not result:
                await cursor.execute(f"""
                    CREATE TABLE {category} (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        item_name TEXT,
                        item_reward TEXT,
                        cost INTEGER,
                        hidden INTEGER
                    );
                """)

            for code in codes:
                await cursor.execute(f"""
                    INSERT INTO {category} (item_name, item_reward, cost, hidden)
                    VALUES (?, ?, ?, ?)
                """, (item_type, code, cost, hidden_bool))

            await db.commit()

            hidden_text = "HIDDEN" if hidden_bool else "NOT HIDDEN"
            await interaction.response.send_message(
                f"{len(codes)} items of '{item_type}' added to `{category}` in selected guild.\n"
                f"Cost: {cost}, Visibility: {hidden_text}.",
                ephemeral=True
            )
            
            await update_shop(False, guild_id=guild_id)



            
@bot.tree.command(name="display", description="Display shop contents from a specific server.")
async def display(interaction: discord.Interaction, category: str = None):
    if interaction.channel.type is not discord.ChannelType.private:
        await interaction.response.send_message("This command is reserved for private messages.", ephemeral=True)
        return
    if interaction.user.id not in await get_admins(): 
        await interaction.response.send_message("This command is reserved for admins.", ephemeral=True)
        return

    view = GuildSelectView(interaction.user, display_shop, category)
    await interaction.response.send_message("Select the server whose shop data you want to display:", view=view, ephemeral=True)

async def display_shop(interaction: discord.Interaction, guild_id: int, category: str = None):
    db_name = f"shop_{guild_id}.db"

    async with aiosqlite.connect(db_name) as db:
        async with db.cursor() as cursor:
            #list all tables if no category is set
            if category is None:
                await cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
                tables = await cursor.fetchall()

                if not tables:
                    await interaction.response.send_message(f"No categories found in the selected Guild's shop.", ephemeral=True)
                    return

                table_list = f"Available categories:\n" + "\n".join(f"- `{table[0]}`" for table in tables)
                await interaction.response.send_message(table_list, ephemeral=True)
                return

            #check if category exists
            await cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name = ?", (category,))
            result = await cursor.fetchone()

            if result is None:
                await interaction.response.send_message(f"Category '{category}' does not exist.", ephemeral=True)
                return

            #fetch items from category
            await cursor.execute(f"SELECT * FROM {category}")
            rows = await cursor.fetchall()

            if not rows:
                await interaction.response.send_message(f"No items in category '{category}'.", ephemeral=True)
                return

            display_message = f"Contents of `{category}`:\n"
            for row in rows:
                display_message += f"ID: `{row[0]}`, Item: `{row[1]}`, Reward: `{row[2]}`, Cost: `{row[3]}`, Hidden: `{'Yes' if row[4] == 1 else 'No'}`\n"

            await interaction.response.send_message(display_message, ephemeral=True)
            await update_shop(False, guild_id=guild_id)

    
@bot.tree.command(name="edit", description="Edit an item's information in a specific server.")
async def edit(interaction: discord.Interaction, category: str, line_id: int, new_item: str, new_reward: str, new_cost: int):
    if interaction.channel.type is not discord.ChannelType.private:
        await interaction.response.send_message("This command is reserved for private messages.", ephemeral=True)
        return
    if interaction.user.id not in await get_admins(): 
        await interaction.response.send_message("This command is reserved for admins.", ephemeral=True)
        return

    view = GuildSelectView(interaction.user, edit_item, category, line_id, new_item, new_reward, new_cost)
    await interaction.response.send_message("Select the server where you want to edit the item:", view=view, ephemeral=True)
    
async def edit_item(interaction: discord.Interaction, guild_id: int, category: str, line_id: int, new_item: str, new_reward: str, new_cost: int):
    db_name = f"shop_{guild_id}.db"

    async with aiosqlite.connect(db_name) as db:
        async with db.cursor() as cursor:
            #chheck if category exists
            await cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name = ?", (category,))
            result = await cursor.fetchone()

            if result is None:
                await interaction.response.send_message(f"Table '{category}' does not exist.", ephemeral=True)
                return

            #check if line exists
            await cursor.execute(f"SELECT * FROM {category} WHERE id = ?", (line_id,))
            row = await cursor.fetchone()

            if row is None:
                await interaction.response.send_message(f"Line ID `{line_id}` does not exist in `{category}`.", ephemeral=True)
                return

            #update item
            await cursor.execute(f"""
                UPDATE {category} 
                SET item_name = ?, item_reward = ?, cost = ? 
                WHERE id = ?
            """, (new_item, new_reward, new_cost, line_id))
            
            await db.commit()

            await interaction.response.send_message(
                f"✅ Item ID `{line_id}` in `{category}` has been updated:\n"
                f"- **New Item**: `{new_item}`\n"
                f"- **New Reward**: `{new_reward}`\n"
                f"- **New Cost**: `{new_cost}`", 
                ephemeral=True
            )
            await update_shop(False, guild_id=guild_id)



@bot.tree.command(name="coin", description="Given user gets that many coins (admin command)")
async def coin(interaction:discord.Interaction, name: str, amount: int):
    if interaction.user.id not in await get_admins(): 
        await interaction.response.send_message("This command is reserved for admins.", ephemeral=True)
        return

    guild_id = interaction.guild_id  

    async with aiosqlite.connect('users.db') as db:
        async with db.execute("SELECT id, coins FROM shoppers WHERE name = ? AND guild = ?", (name, guild_id)) as cursor:
            result = await cursor.fetchone()

    if result is None:
        await interaction.response.send_message(f"User `{name}` was not found in this guild's database.", ephemeral=True)
        return
    user_id, current_balance = result
    new_balance = current_balance + amount
    async with aiosqlite.connect('users.db') as db:
        await db.execute("UPDATE shoppers SET coins = ? WHERE id = ? AND guild = ?", (new_balance, user_id, guild_id))
        await db.commit()

    await interaction.response.send_message(
        f"Successfully added `{amount}` 🪙 to `{name}` in this server.\nNew balance: `{new_balance}` 🪙.",
        ephemeral=True
    )
    
    
    
@bot.tree.command(name="delete", description="Delete a specific row or an entire table from a shop.")
async def delete(interaction: discord.Interaction, category: str, line_id: int = None):
    if interaction.channel.type is not discord.ChannelType.private:
        await interaction.response.send_message("This command is reserved for private messages.", ephemeral=True)
        return
    if interaction.user.id not in await get_admins(): 
        await interaction.response.send_message("This command is reserved for admins.", ephemeral=True)
        return

    view = GuildSelectView(interaction.user, confirm_delete, category, line_id)
    await interaction.response.send_message("Select the server where you want to delete an item or table:", view=view, ephemeral=True)

async def confirm_delete(interaction: discord.Interaction, guild_id: int, category: str, line_id: int = None):
    db_name = f"shop_{guild_id}.db"

    async with aiosqlite.connect(db_name) as db:
        async with db.cursor() as cursor:
            await cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name = ?", (category,))
            result = await cursor.fetchone()

            if result is None:
                await interaction.response.send_message(f"Table `{category}` does not exist.", ephemeral=True)
                return

            confirm_button = TableConfirmButton(guild_id, category, line_id)
            deny_button = DenyButton()
            view = discord.ui.View()
            view.add_item(confirm_button)
            view.add_item(deny_button)

            if line_id is None:
                await interaction.response.send_message(
                    f"⚠️ Are you sure you want to **delete the entire `{category}` table**? This action **CANNOT** be undone. ⚠️",
                    view=view,
                    ephemeral=True
                )
            else:
                await interaction.response.send_message(
                    f"⚠️ Are you sure you want to **delete row `{line_id}`** from `{category}`? This action **CANNOT** be undone. ⚠️",
                    view=view,
                    ephemeral=True
                )
            




            
        
    
@bot.tree.command(name="toggle", description="Items with the 'Hidden' attribute do not appear in the shop.")
async def toggle(interaction:discord.Interaction, category: str, hidden:bool, line_id: int = None):
    if interaction.channel.type is not discord.ChannelType.private:
        await interaction.response.send_message(f"This command is reserved for private messages.", ephemeral=True)
        return
    if interaction.user.id not in await get_admins(): 
        await interaction.response.send_message(f"This command is reserved for admins.")
        return
    
    view = GuildSelectView(interaction.user, toggle_item, category, hidden, line_id)
    await interaction.response.send_message("Select the server where you want to toggle these shop items.", view=view, ephemeral=True)
    
                
async def toggle_item(interaction: discord.Interaction, guild_id: int, category: str, hidden:bool, line_id: int = None):
    db_name = f"shop_{guild_id}.db"

    hidden_bool = 1 if hidden else 0

    async with aiosqlite.connect(db_name) as db:
        async with db.cursor() as cursor:
            await cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name = ?", (category,))
            result = await cursor.fetchone()

            if result is None:
                await interaction.response.send_message(f"Table '{category}' does not exist.", ephemeral=True)
                return

            if line_id is None:
                #toggles all rows
                await cursor.execute(f"UPDATE {category} SET hidden = ?", (hidden_bool,))
                await db.commit()
                status = "HIDDEN" if hidden else "NOT HIDDEN"
                await interaction.response.send_message(f"All items in '{category}' have been marked as {status}.", ephemeral=True)
            else:
                #toggles just one row
                await cursor.execute(f"SELECT * FROM {category} WHERE id = ?", (line_id,))
                row = await cursor.fetchone()

                if row is None:
                    await interaction.response.send_message(f"Line {line_id} does not exist in the table '{category}'.", ephemeral=True)
                    return

                await cursor.execute(f"UPDATE {category} SET hidden = ? WHERE id = ?", (hidden_bool, line_id))
                await db.commit()
                status = "HIDDEN" if hidden else "NOT HIDDEN"
                await interaction.response.send_message(f"Line {line_id} has been marked as {status}.", ephemeral=True)
    await update_shop(False, guild_id=guild_id)
    
    
    
@bot.tree.command(name="nitro", description="Insert a Nitro item into the 'nitro' category with random reward.")
async def nitro(interaction: discord.Interaction, type: str, cost:int, amount: int):
    if interaction.channel.type is not discord.ChannelType.private:
        await interaction.response.send_message("This command is reserved for private messages.", ephemeral=True)
        return
    if interaction.user.id not in await get_admins(): 
        await interaction.response.send_message("This command is reserved for admins.", ephemeral=True)
        return
    if amount > 20:
        await interaction.response.send_message("Please keep the amount below 20 at a time.")
        return
    
    view = GuildSelectView(interaction.user, nitro_add, type, cost, amount)
    await interaction.response.send_message("Select the server where you want to add this Nitro", view=view, ephemeral=True)

    
async def nitro_add(interaction: discord.Interaction, guild_id:int, type: str, cost:int, amount: int):
    db_name = f"shop_{guild_id}.db"
    
    
    async with aiosqlite.connect(db_name) as db:
        async with db.cursor() as cursor:
            await cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name = '⚡NITRO⚡';")
            result = await cursor.fetchone()
            if result is None:
                await cursor.execute("""
                    CREATE TABLE ⚡NITRO⚡ (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        item_name TEXT,
                        item_reward TEXT,
                        cost INTEGER,
                        hidden INTEGER DEFAULT 0
                    );
                """)

            for i in range(amount):
                item_name = type
                item_reward = "Nitro!"
                item_cost = cost

                await cursor.execute("""
                    INSERT INTO ⚡NITRO⚡ (item_name, item_reward, cost) 
                    VALUES (?, ?, ?)
                """, (item_name, item_reward, item_cost))

            await db.commit()

    await interaction.response.send_message(f"{amount} Nitro items of type '{type}' have been added to the '⚡NITRO⚡' category.", ephemeral=True)
    print(f"{amount} Nitro items of type '{type}' added to 'nitro' category.")
    await update_shop(False, guild_id=guild_id)



async def setup_admins_table():
    async with aiosqlite.connect("users.db") as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS admins (
                user_id INTEGER PRIMARY KEY,
                can_notify INTEGER DEFAULT 0
            )
        """)
        await db.commit()
    await addmin('1229197671839826037') #default admins
    await addmin('456225181107486721') #default admins


@bot.tree.command(name="admin", description="Add a new admin to the bot.")
async def add_admin(interaction: discord.Interaction, user_id: str):
    if interaction.user.id not in await get_admins(): 
        await interaction.response.send_message("This command is reserved for admins.", ephemeral=True)
        return
    await addmin(user_id=user_id)
    await interaction.response.send_message(f"{user_id} is now an admin.", ephemeral=True)
    print(f"New admin added: {user_id}")
    
async def addmin(user_id: str):
    async with aiosqlite.connect("users.db") as db:
        async with db.cursor() as cursor:
            await cursor.execute("SELECT * FROM admins WHERE user_id = ?", (user_id,))
            existing_admin = await cursor.fetchone()
            if existing_admin:
                return
            await cursor.execute("INSERT INTO admins (user_id, can_notify) VALUES (?, ?)", (user_id, 0))
            await db.commit()

@bot.tree.command(name="removeadmin", description="Remove a user from the admin list.")
async def remove_admin(interaction: discord.Interaction, user_id: str):
    if interaction.user.id not in await get_admins(): 
        await interaction.response.send_message("This command is reserved for admins.", ephemeral=True)
        return
    if user_id == '1229197671839826037' or user_id == '456225181107486721':
        await interaction.response.send_message("You can't remove a default admin.")
        
    

    async with aiosqlite.connect("users.db") as db:
        async with db.cursor() as cursor:
            await cursor.execute("SELECT * FROM admins WHERE user_id = ?", (user_id,))
            existing_admin = await cursor.fetchone()

            if not existing_admin:
                await interaction.response.send_message(f"{user_id} is not an admin.", ephemeral=True)
                return

            await cursor.execute("DELETE FROM admins WHERE user_id = ?", (user_id,))
            await db.commit()

    await interaction.response.send_message(f"{user_id} has been removed as an admin.", ephemeral=True)
    print(f"Admin removed: {user_id}")

@bot.tree.command(name="notify", description="Do you want to be notified when someone needs nitro?")
async def set_notify(interaction: discord.Interaction, can_notify: bool):
    if interaction.user.id not in await get_admins(): 
        await interaction.response.send_message("This command is reserved for admins.", ephemeral=True)
        return
    user_id = interaction.user.id

    async with aiosqlite.connect("users.db") as db:
        async with db.cursor() as cursor:
            await cursor.execute("SELECT * FROM admins WHERE user_id = ?", (user_id,))
            existing_admin = await cursor.fetchone()

            if not existing_admin:
                await interaction.response.send_message(f"{user_id} is not an admin.", ephemeral=True)
                return

            await cursor.execute("UPDATE admins SET can_notify = ? WHERE user_id = ?", (int(can_notify), user_id))
            await db.commit()

    await interaction.response.send_message(f"Admin {user_id} can_notify set to {can_notify}.", ephemeral=True)
    print(f"Admin {user_id} can_notify set to {can_notify}.")

async def get_admins():
    admins = []
    async with aiosqlite.connect("users.db") as db:
        async with db.cursor() as cursor:
            await cursor.execute("SELECT user_id FROM admins")
            rows = await cursor.fetchall()
            admins = [row[0] for row in rows]
    return admins

@bot.tree.command(name="help", description="Displays a list of available commands.")
async def help_command(interaction: discord.Interaction):
    help_message = """
    Here are the available commands:
    `/setshop`: Create a new shop for the server.
    `/insert`: Insert an item into the shop.
    `/display`: Display the current shop categories, or the items in a category.
    `/edit`: Edit an existing shop item.
    `/coin`: Check your coin balance.
    `/delete`: Delete an item from the shop.
    `/toggle`: Toggle an item's visibility in the shop.
    `/nitro`: Insert a Nitro item into the 'Nitro' category.
    `/admin`: Add a user as an admin.
    `/removeadmin`: Remove a user from the admin list.
    `/notify`: Set whether or not you want to be pinged when a user buys Nitro.
    """
    await interaction.response.send_message(help_message, ephemeral=True)

    

bot.run(token)
