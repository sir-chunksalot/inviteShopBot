import discord
from datetime import datetime, timezone
from discord.ext import commands
from discord.ui import Button, View, Select
import aiosqlite
import ast
from collections import defaultdict
from discord import app_commands
import json

from discord import Embed

token = "MTM0MzM4MjQ5ODkxODQwNDIyNg.GeyYtG.lJ_lPBPNvxfZuZIV5ffaKsUdjoXEzMGsZ9WT1Y"

admin = [1229197671839826037, 456225181107486721]

invite_shop_helper = 1342337584860233788

subscription_plans = {}
embed = None
msg = None
multiplier = 10
intents = discord.Intents.all()
bot = commands.Bot(command_prefix='/', intents=intents)


INVITE_FILE = 'main/invites.txt'


@bot.event
async def on_ready():
    print("Registered commands:")
    for command in bot.tree.get_commands():
        print(command.name)

    await bot.tree.sync()
    await get_plans()
    print(f'We have logged in as {bot.user}')
    async with aiosqlite.connect("user_invites.db") as db:
        async with db.cursor() as cursor:
            await cursor.execute('CREATE TABLE IF NOT EXISTS users (row_id INTEGER PRIMARY KEY AUTOINCREMENT, id INTEGER, name STRING, invites INTEGER, guild INTEGER, coins INTEGER, UNIQUE (id, guild))')
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
                            INSERT INTO users (id, name, invites, guild, coins)
                            VALUES (?, ?, 0, ?, 0)
                            ON CONFLICT(id, guild) DO NOTHING
                        """, (user_id, member.name, guild_id))
                        
                    invites = await guild.invites()
                    for invite in invites:
                        user = invite.inviter.id  #userid for the inviter. be careful, one user can have multiple invite links
                        invite_count = invite.uses  #number of uses for this individual invite. 
                        print(invite)

                        await cursor.execute("""
                            INSERT INTO users (id, name, invites, guild, coins)
                            VALUES (?, ?, ?, ?, 0)
                            ON CONFLICT(id, guild) DO UPDATE SET
                                invites = invites + EXCLUDED.invites
                        """, (user, invite.inviter.name, invite_count, guild_id))
                    await db.commit()
                    
                except Exception as e:
                    print(f"Error processing invites for guild {guild.name}: {e}")
    await update_shop(False)
class ShopView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)  # Make it persistent
        self.add_item(GuideButton())
        self.add_item(BalanceButton())

        # Add category buttons (1-5)
        for i in range(1, 6):
            self.add_item(CategorySelect(emoji=f"{i}️⃣", value=i))                   

@bot.event
async def on_message(message):
    global subscription_plans
    
    if message.author.id != invite_shop_helper:
        return
    if message.content.startswith("<PLANS>"):
        sub_plans = message.content[7:]
        data_dict = ast.literal_eval(sub_plans)
        subscription_plans = data_dict
        await bot.tree.sync()
    if message.content.startswith("<PAYMENT_DETAILS>"):
        message_info = message.content.split('|')
        user_id = int(message_info[1]) 
        selected_plan = message_info[2]
        shop_cost = int(message_info[3])
        count = int(message_info[4])
        status = message_info[5]
        
        if status == "False":
            user = await bot.fetch_user(user_id)
            await user.send("Purchase Failed. Please Try again later.")
        else:
            user = await bot.fetch_user(user_id)
            await user.send("Purchase success!")
            async with aiosqlite.connect('shop.db') as db:

                async with db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name = 'Nitro';") as cursor:
                    table = await cursor.fetchone()

                if table is None:
                    await db.execute("""
                        CREATE TABLE Nitro (
                            id INTEGER PRIMARY KEY AUTOINCREMENT,
                            item_name TEXT NOT NULL,
                            item_reward TEXT NOT NULL,
                            cost INTEGER NOT NULL,
                            hidden INTEGER NOT NULL
                        );
                    """)
                    await db.commit()

                for i in range(count):
                    await db.execute(
                        "INSERT INTO Nitro (item_name, item_reward, cost, hidden) VALUES (?, ?, ?, ?)",
                        (selected_plan, f"Nitro_Gift_{selected_plan}", shop_cost, 0)  
                    )
                await db.commit()

            await update_shop(False)
            
            print(f"Item `{selected_plan}` added {count} times to the Nitro table with cost `{shop_cost}`.")
            
        
 
@bot.event
async def on_guild_join(guild):
    print('joined new guild')
    channel = next((channel for channel in guild.text_channels if channel.permissions_for(guild.me).send_messages), None)
    if channel:
        await channel.send('Hello! If you\'d like to get started, please type `/setshop` in the appropriate channel.')
    else:
        print("No suitable text channel found to send the message.")
        
@bot.event
async def on_member_join(member): 
    guild = member.guild
    guild_id = guild.id
    invites = await guild.invites()
    inviteTracking = {}
    user = None
    new_member = False
    row_id = None  # Track the new row_id
    
    for invite in invites:
        inviteTracking[invite.inviter.id] = inviteTracking.get(invite.inviter.id, 0) + invite.uses
    print(inviteTracking)
    
    async with aiosqlite.connect("user_invites.db") as db:
        async with db.cursor() as cursor:
            await cursor.execute("SELECT id, invites FROM users WHERE guild = ?", (guild_id,))
            db_users = await cursor.fetchall()
            
            # Find who invited the new member
            for user_id, db_invites in db_users:
                if user_id in inviteTracking:
                    new_invites = inviteTracking[user_id]
                    if db_invites < new_invites:
                        print(f"User {user_id} has fewer invites in DB ({db_invites}) than in the new data ({new_invites})")
                        user = user_id  # This is the inviter
                        await cursor.execute("""
                            UPDATE users
                            SET invites = ?
                            WHERE id = ? AND guild = ?
                        """, (new_invites, user_id, guild_id))
                        
            # Check if the new member is already in the database
            await cursor.execute("SELECT rowid FROM users WHERE id = ? AND guild = ?", (member.id, guild_id))
            db_member = await cursor.fetchone()
            
            if db_member is None:  # If the member doesn't exist, insert them and get rowid
                new_member = True
                print(f"Adding new user {member.id} to the database")
                
                await cursor.execute("""
                    INSERT INTO users (id, name, invites, guild, coins)
                    VALUES (?, ?, 0, ?, 0)
                """, (member.id, member.name, guild_id))

                # Fetch the last inserted rowid
                await cursor.execute("SELECT last_insert_rowid()")
                row_id = (await cursor.fetchone())[0]
                print(f"New row_id for {member.id} is {row_id}")
                    
            await db.commit()

    # Award coins if user invited the new member
    if user is not None and new_member:
        print(f"{user} gained currency")
        coins = 1 * multiplier
        async with aiosqlite.connect("user_invites.db") as db:
            async with db.cursor() as cursor:
                await cursor.execute("""
                    UPDATE users
                    SET coins = coins + ?
                    WHERE id = ? AND guild = ?
                """, (coins, user, guild_id,))
            await db.commit()
    else: 
        print('No valid user found')


    
    
@bot.event
async def on_invite_create(invite): #refreshes the table everytime a new invite is made, this makes sure invites dont fall through the cracks when they expire or some admin deletes them
    async with aiosqlite.connect("user_invites.db") as db:
        async with db.cursor() as cursor:
            invites = await invite.guild.invites()
            for invite in invites:
                user = invite.inviter.id  
                invite_count = invite.uses  
                guild_id = invite.guild.id
                
                await cursor.execute("""
                    UPDATE users
                    SET invites = ?
                    WHERE id = ? AND guild = ?
                """, (invite_count, user, guild_id,))
        await db.commit()

        
@bot.tree.command(name="setshop")
async def setshop(interaction:discord.Interaction):
    if interaction.user.id not in admin:
        await interaction.response.send_message(f"This command is reserved for admins.", ephemeral=True)
        return
    await interaction.response.send_message("Shop created", ephemeral=True)
    print('Shop has been set.')
    await update_shop(True, interaction=interaction)


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
        
async def get_shop_message(guild_id):
    try:
        with open(SHOP_MESSAGE_FILE, "r") as f:
            data = json.load(f)
        return data.get(str(guild_id))  
    except (FileNotFoundError, json.JSONDecodeError):
        return None

async def get_all_shop_messages():
    """Retrieve all saved shop messages for all guilds."""
    try:
        with open(SHOP_MESSAGE_FILE, "r") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}  # Return an empty dict if the file is missing/corrupt

async def update_shop(new: bool, interaction:discord.Interaction=None):
    global embed
    embed = Embed(
        color=discord.Color.dark_blue(),
        title='💰 Welcome to the `Invite Shop` 💰',
        description="Click on a category to see available items! Check your balance with the 🪙 button.\nConfused? Click on the 📝!"
    )

    async with aiosqlite.connect('shop.db') as db:
        async with db.execute("SELECT name FROM sqlite_master WHERE type='table';") as cursor:
            tables = await cursor.fetchall()

    category_buttons = []
    visible_count = 0  # Track the number of displayed categories

    for table in tables:
        if visible_count >= 5:  # Ensure we only show up to 5 categories
            break

        category = table[0]
        if category == "sqlite_sequence":
            continue

        async with aiosqlite.connect('shop.db') as db:
            async with db.execute(f"SELECT * FROM {category} WHERE hidden = 0") as cursor:
                items = await cursor.fetchall()

        if not items:  # Skip empty tables
            continue

        visible_count += 1  # Only count categories that have items

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

        for item_name, details in list(item_grouped.items())[:5]:
            embed.add_field(
                name=f"`{item_name}`🛒",
                value=f"\n> Cost: `{details['cost']}` 🪙\n> Stock: `{details['stock']}` ",
                inline=True
            )

        embed.add_field(name="", value=f"*Click `{visible_count}` to view more items in this category.*", inline=True)

        category_buttons.append(
            CategorySelect(style=discord.ButtonStyle.blurple, emoji=f"{visible_count}️⃣", tables=tables, value=visible_count)
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
        guild_id = interaction.guild_id
        msg = await interaction.channel.send(embed=embed, view=view)
        await save_shop_message(guild_id, interaction.channel.id, msg.id)
        return

    for guild_id, data in shop_data.items():
        guild = bot.get_guild(int(guild_id))
        if not guild:
            print(f"Bot is no longer in guild {guild_id}, skipping...")
            continue

        channel_id, message_id = data["channel_id"], data["message_id"]
        channel = bot.get_channel(channel_id)
        if not channel:
            print(f"Channel {channel_id} not found in guild {guild_id}, skipping...")
            continue

        try:
            msg = await channel.fetch_message(message_id)
            await msg.edit(embed=embed, view=view)
            print(f"Shop updated for guild {guild_id}.")
        except discord.NotFound:
            print(f"Shop message {message_id} not found in guild {guild_id}. It may have been deleted.")
        except discord.Forbidden:
            print(f"Missing permissions to edit message {message_id} in guild {guild_id}.")


class PurchaseDropdown(Select):
    def __init__(self, items, category):
        options = [
            discord.SelectOption(label=item_name, value=str(item_id), description=f"Cost: {details['cost']} 🪙 | Stock: {details['stock']}")
            for item_id, (item_name, details) in enumerate(items.items(), start=1)
        ]

        super().__init__(placeholder="Select an item to purchase...", min_values=1, max_values=1, options=options)
        self.items = items
        self.category = category

    async def callback(self, interaction):
        selected_id = int(self.values[0])
        item_name = list(self.items.keys())[selected_id - 1]
        details = self.items[item_name]

        # Process the purchase logic here (you might want to replace this with a proper function)
        view =  View()
        confirm_button = ShopConfirmButton(self.category, details['item_id'], details['cost'], item_name)
        deny_button = DenyButton()
        view.add_item(confirm_button)
        view.add_item(deny_button)
        await interaction.response.send_message(f"You are trying to purchase {item_name} for {details['cost']}. Are you sure you want to do this?", view=view, ephemeral=True)


class CategorySelect(Button):
    def __init__(self, style, emoji, tables, value):
        super().__init__(style=style, emoji=emoji, custom_id=f"category_{value - 1}")
        self.tables = tables
        self.value = value - 1  # Adjust for 0-based index

    async def callback(self, interaction):
        embed = discord.Embed(
            color=discord.Color.dark_blue(),
            title='`Available for Purchase`:',
            description=""
        )

        # Fetch the correct category based on the button clicked
        category = self.tables[self.value][0]
        print(category)
        async with aiosqlite.connect('shop.db') as db:
            try:
                async with db.execute(f"SELECT * FROM {category}") as cursor:
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

                # Populate the embed with available items
                for count, (item_name, details) in enumerate(item_grouped.items(), start=1):
                    embed.add_field(
                        name=f" Item `{count}`: {item_name}    ",
                        value=f"Cost: `{details['cost']}` 🪙\nStock: {details['stock']} ",
                        inline=True
                    )

                view = View()
                view.add_item(PurchaseDropdown(item_grouped, category))

                await interaction.response.send_message(f"Here are the items available for purchase in the `{category}` category:", embed=embed, view=view, ephemeral=True)

            except Exception as e:
                print(f"Error fetching items from category {category}: {e}")
                await interaction.response.send_message(f"An error occurred while fetching items from the category `{category}`.", ephemeral=True)


class ShopConfirmButton(Button):
    def __init__(self, category, line_id, item_cost, item_name):
        super().__init__(style=discord.ButtonStyle.green, emoji='✅')
        self.category = category 
        self.line_id = line_id 
        self.item_cost = item_cost
        self.item_name = item_name

    async def callback(self, interaction):
        user_id = interaction.user.id

        async with aiosqlite.connect('user_invites.db') as db:
            async with db.execute("SELECT coins FROM users WHERE id = ?", (user_id,)) as cursor:
                result = await cursor.fetchone()

        if result is None:
            await interaction.response.send_message("You don't have an account yet. Try clicking the help button on the shop to get started.", ephemeral=True)
            return

        user_balance = result[0]

        if user_balance < self.item_cost:
            await interaction.response.send_message("You don't have enough coins to buy this item. Click the 🪙 button on the shop to check your balance.", ephemeral=True)
            return

        #fetch reward
        async with aiosqlite.connect('shop.db') as db:
            async with db.execute(f"SELECT item_reward FROM {self.category} WHERE id = ?", (self.line_id,)) as cursor:
                reward_result = await cursor.fetchone()

        if reward_result is None:
            await interaction.response.send_message("This item does not exist anymore.", ephemeral=True)
            return

        item_reward = reward_result[0] 

        #deduct moneys and update the db
        new_balance = user_balance - self.item_cost
        async with aiosqlite.connect('user_invites.db') as db:
            await db.execute("UPDATE users SET coins = ? WHERE id = ?", (new_balance, user_id))
            await db.commit()

        # Send confirmation message with the reward
        try:
            await interaction.response.send_message("Purchase successful. Please check your DM's", ephemeral=True)
            await interaction.user.send(
                f"Purchase successful! You bought `{self.item_name}` for `{self.item_cost}` 🪙.\n"
                f"You received: `{item_reward}` 🎁.\n"
                f"Your new balance is `{new_balance}` 🪙.",
            )
            #if item reward is Nitro_Gift_ then call "Gift Nitro" method
            if item_reward[:11] == "Nitro_Gift_":
                await gift_nitro(interaction.user.id, self.item_name)
        except discord.Forbidden:
            #in case user has dms disabled
            await interaction.response.send_message(
                "Purchase failed. Please allow 'Safe Direct Messaging' in your user settings.",
                ephemeral=True
            )
            new_balance = user_balance + self.item_cost #give money back
            async with aiosqlite.connect('user_invites.db') as db:
                await db.execute("UPDATE users SET coins = ? WHERE id = ?", (new_balance, user_id))
                await db.commit()
                return
        except discord.HTTPException as e:
            await interaction.response.send_message(
                f"Purchase failed. Please try again later.",
                ephemeral=True
            )
            new_balance = user_balance + self.item_cost #give money backl
            async with aiosqlite.connect('user_invites.db') as db:
                await db.execute("UPDATE users SET coins = ? WHERE id = ?", (new_balance, user_id))
                await db.commit()
                return
            return
        
        await delete_line(self.category, self.line_id)  # Remove item from stock

async def gift_nitro(user_id: int, selected_plan:str):
    helper = await bot.fetch_user(invite_shop_helper)
    await helper.send(f"/gift|{user_id}|{selected_plan}")
    print("tried gifting nitro")
    
    

class DenyButton(Button):
    def __init__(self):
        super().__init__(style=discord.ButtonStyle.red, emoji='✖️')
    async def callback(self, interaction):
        await interaction.response.send_message("Action cancelled.", ephemeral=True)
class TableConfirmButton(Button):
    global category
    global line_id
    
    def __init__(self, category:str, line_id:int = None):
        super().__init__(style=discord.ButtonStyle.green, emoji='✅')
        self.category = category
        self.line_id = line_id
        
    async def callback(self, interaction: discord.Interaction):
        if self.line_id == None: #table delete
            await delete_table(self.category)
            await interaction.response.send_message(f"The table '{self.category}' has been deleted.", ephemeral=True)

        else: #line delete
            await  delete_line(self.category, self.line_id)
            await interaction.response.send_message(f"Line {self.line_id} has been deleted from the '{self.category}' table.", ephemeral=True)

class GuideButton(Button):
    def __init__(self):
        super().__init__(style=discord.ButtonStyle.gray, emoji='📝', custom_id="guide_button")
    async def callback(self, interaction):
        await interaction.response.send_message("**How does this bot work?**\nThis shop operates with `Invite Tokens`.\n\nYou gain these tokens by inviting new users to this server.\n\n**How do I invite people to the server?**\n-Click the dropdown next to the servers name in the top left.\n-Next, click `Invite People`.\n-Click any user on your friends list. \n-As soon as a new user accepts one of your invites, you will be automatically awarded with currency!\n\n**How do I see how much money I have?**\nClick the 🪙 button underneath the shop.\n\n**Where is my purchase?**\n-To maintain security, all purchase codes are sent to your DM's. If you didn't get a message, its likely you have set 'Allow DM's from other server member' to false. Don't worry, you have been refunded.\n\n**My question isn't listed!**\n-Please message `thedapperlad` any further questions you have.", ephemeral=True)
class Next(Button):
    global index 
    def __init__(self):
        super().__init__(emoji='⏭️')
    
    async def callback(self, interaction):
        print(f'value=')
class BalanceButton(Button):
    def __init__(self):
        super().__init__(style=discord.ButtonStyle.gray, emoji='🪙')
    
    async def callback(self, interaction):
        user_id = interaction.user.id  
        guild_id = interaction.guild.id 
        
        async with aiosqlite.connect("user_invites.db") as db:
            async with db.cursor() as cursor:
                await cursor.execute("SELECT coins FROM users WHERE id = ? AND guild = ?", (user_id, guild_id))
                result = await cursor.fetchone() 
                
        if result:
            coins = result[0] 
            await interaction.response.send_message(f"Your current balance is: 🪙 {coins}", ephemeral=True)
        else:
            await interaction.response.send_message("You don't have a balance yet.", ephemeral=True)


async def delete_table(category: str):
    async with aiosqlite.connect("shop.db") as db:
        async with db.cursor() as cursor:
            await cursor.execute(f"DROP TABLE {category}")
            await db.commit()
    await update_shop(False)
async def delete_line(category: str, line_id: int):
    async with aiosqlite.connect("shop.db") as db:
        async with db.cursor() as cursor:
            await cursor.execute(f"DELETE FROM {category} WHERE id = ?", (line_id,))
            await db.commit()
    await update_shop(False)

    
@bot.tree.command(name="insert", description="Ex: Giftcards Giftcard xyz,abc,qwe, 15 False")
async def insert(interaction:discord.Interaction, category: str, item_type: str, item_reward: str, cost: int, hidden: bool):
    if interaction.channel.type is not discord.ChannelType.private:
        await interaction.response.send_message(f"This command is reserved for private messages.", ephemeral=True)
        return
    if interaction.user.id not in admin:
        await interaction.response.send_message(f"This command is reserved for admins.")
        return
        
    hidden_bool = 0 #bc sqlite tables dont like bools
    if hidden:
        hidden_bool = 1
        
    codes = [code.strip() for code in item_reward.split(',')]
        
    print("Tried to insert a new item into the table.")
    async with aiosqlite.connect("shop.db") as db:
        async with db.cursor() as cursor:
            await cursor.execute("""
                SELECT name FROM sqlite_master WHERE type='table' AND name = ?;
            """, (category,))
            result = await cursor.fetchone()

            if not result:
                print(f"Creating a new table for category: {category}")
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
            
            hidden_text = "NOT HIDDEN"
            if hidden_bool == 1:
                hidden_text = "HIDDEN"
            await interaction.response.send_message(f"{len(codes)} items of '{item_type}' type have been added to the '{category}' category. The cost is {cost} and the item is currently {hidden_text}.")
    await update_shop(False)
            
@bot.tree.command(name="display")
async def display(interaction:discord.Interaction, category: str = None):
    if interaction.channel.type is not discord.ChannelType.private:
        await interaction.response.send_message(f"This command is reserved for private messages.", ephemeral=True)
        return
    if interaction.user.id not in admin:
        await interaction.response.send_message(f"This command is reserved for admins.")
        return
    
    async with aiosqlite.connect("shop.db") as db:
        async with db.cursor() as cursor:
            #list all tables if no specific table is listed
            if category is None:
                await cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
                tables = await cursor.fetchall()
                
                if not tables:
                    await interaction.response.send_message("No tables found in the database.", ephemeral=True)
                    return
                
                table_list = "Available categories:\n"
                for table in tables:
                    table_list += f"- `{table[0]}`\n"
                
                await interaction.response.send_message(table_list)
                return
            
            await cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name = ?", (category,))
            result = await cursor.fetchone()

            if result is None:  
                await interaction.response.send_message(f"Table '{category}' does not exist.", ephemeral=True)
                return

            await cursor.execute(f"SELECT * FROM {category}")
            rows = await cursor.fetchall()


            if not rows:
                await interaction.response.send_message(f"No data found in table '{category}'.", ephemeral=True)
                return

            display_message = f"Contents of `{category}` table:\n"
            for row in rows:
                display_message += f"ID: `{row[0]}`, Item: `{row[1]}`, Reward: `{row[2]}`, Cost: `{row[3]}`, Hidden: `{'Yes' if row[4] == 1 else 'No'}`\n"
            
            await interaction.response.send_message(display_message)
    
@bot.tree.command(name="edit", description="Edit a specific items information.")
async def edit(interaction:discord.Interaction, category: str, line_id: int, new_item:str, new_reward:str, new_cost:int):
    if interaction.channel.type is not discord.ChannelType.private:
        await interaction.response.send_message(f"This command is reserved for private messages.", ephemeral=True)
        return
    if interaction.user.id not in admin:
        await interaction.response.send_message(f"This command is reserved for admins.")
        return
    
    async with aiosqlite.connect("shop.db") as db:
        async with db.cursor() as cursor:
            await cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name = ?", (category,))
            result = await cursor.fetchone()

            if result is None:  #if table isnt real
                await interaction.response.send_message(f"Table '{category}' does not exist.", ephemeral=True)
                return
            

            await cursor.execute(f"SELECT * FROM {category} WHERE id = ?", (line_id,))
            row = await cursor.fetchone()
            
            if row is None:  #if line id isnt real
                await interaction.response.send_message(f"Line ID '{line_id}' does not exist in table '{category}'.", ephemeral=True)
                return
            
            #update stuff
            await cursor.execute(f"""
                UPDATE {category} 
                SET item_name = ?, item_reward = ?, cost = ? 
                WHERE id = ?
            """, (new_item, new_reward, new_cost, line_id))
            
            await db.commit()

            await interaction.response.send_message(f"Item ID `{line_id}` in '{category}' has been updated:\n- New Item: `{new_item}`\n- New Reward: `{new_reward}`\n- New Cost: `{new_cost}`")
    await update_shop(False)

@bot.tree.command(name="coin", description="Given user gets that many coins (dev command)")
async def coin(interaction:discord.Interaction, name: str, amount: int):
    if interaction.user.id not in admin:
        await interaction.response.send_message(f"This command is reserved for admins.")
        return

    async with aiosqlite.connect('user_invites.db') as db:
        async with db.execute("SELECT id, coins FROM users WHERE name = ?", (name,)) as cursor:
            result = await cursor.fetchone()
    if result is None:
        await interaction.response.send_message(f"User `{name}` was not found in the database.", ephemeral=True)
        return
    user_id, current_balance = result
    new_balance = current_balance + amount

    async with aiosqlite.connect('user_invites.db') as db:
        await db.execute("UPDATE users SET coins = ? WHERE id = ?", (new_balance, user_id))
        await db.commit()

    await interaction.response.send_message(f"Successfully added `{amount}` 🪙 to `{name}`.\nNew balance: `{new_balance}` 🪙.", ephemeral=True)
    
    
    
@bot.tree.command(name="delete", description="Delete the specified table or just a line from that table.")
async def delete(interaction:discord.Interaction, category: str, line_id: int = None):
    if interaction.channel.type is not discord.ChannelType.private:
        await interaction.response.send_message(f"This command is reserved for private messages.", ephemeral=True)
        return
    if interaction.user.id not in admin:
        await interaction.response.send_message(f"This command is reserved for admins.")
        return
    
    #delete certain element from table, or entire table if line number isnt provided. prompt user with an "are you sure"
    
    async with aiosqlite.connect("shop.db") as db:
        async with db.cursor() as cursor:
            #confirm table exists
            await cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name = ?", (category,))
            result = await cursor.fetchone()

            if result is None:
                await interaction.response.send_message(f"Table '{category}' does not exist.", ephemeral=True)
                return

            if line_id is None:
                #yes and no buttons because we fancy in here
                confirm_button = TableConfirmButton(category=category, line_id=line_id)
                deny_button = DenyButton()
                view = discord.ui.View()
                view.add_item(confirm_button)
                view.add_item(deny_button)

                await interaction.response.send_message(f"Are you sure you want to delete the **entire** table '{category}'? This action cannot be undone.", view=view, ephemeral=True)
                return
            
            else:
                await cursor.execute(f"SELECT * FROM {category} WHERE id = ?", (line_id,))
                row = await cursor.fetchone()

                if row is None:
                    await interaction.response.send_message(f"Line {line_id} does not exist in the table '{category}'.", ephemeral=True)
                    return

                confirm_button = TableConfirmButton(category=category, line_id=line_id)
                deny_button = DenyButton()
                view = discord.ui.View()
                view.add_item(confirm_button)
                view.add_item(deny_button)

                await interaction.response.send_message(f"Are you sure you want to delete line {line_id} from the '{category}' table? This action cannot be undone.", view=view, ephemeral=True)
                return
            
        
    
@bot.tree.command(name="toggle", description="Items with the 'Hidden' attribute do not appear in the shop.")
async def toggle(interaction:discord.Interaction, category: str, hidden:bool, line_id: int = None):
    if interaction.channel.type is not discord.ChannelType.private:
        await interaction.response.send_message(f"This command is reserved for private messages.", ephemeral=True)
        return
    if interaction.user.id not in admin:
        await interaction.response.send_message(f"This command is reserved for admins.")
        return
    
    #toggle certain element from table, or entire table if line number isnt provided. 
    hidden_bool = 1 if hidden else 0

    async with aiosqlite.connect("shop.db") as db:
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
    await update_shop(False)
                
                
@bot.tree.command(name = "plans")
async def plans(interaction:discord.Interaction):
    global subscription_plans
    
    if interaction.channel.type is not discord.ChannelType.private:
        await interaction.response.send_message(f"This command is reserved for private messages.", ephemeral=True)
        return
    if interaction.user.id not in admin:
        await interaction.response.send_message(f"This command is reserved for admins.")
        return
    formatted_text = "\n".join([f"**{key}**: `{value}`" for key, value in subscription_plans.items()])
    await interaction.response.send_message(f"Here are the available plans:\n{formatted_text}") 
    await get_plans()
    
    
async def get_plans():
    helper = await bot.fetch_user(invite_shop_helper) 
    await helper.send("/plans")
    

@bot.tree.command(name="purchase", description="Purchase an item")
async def purchase(interaction: discord.Interaction, amount: int, shop_cost: int):
    # Ensure subscription_plans is not empty
    if not subscription_plans:
        await interaction.response.send_message("If you're seeing this this means either `InviteShopBot` or `InviteShopHelper` are not fully online, wait for them to finish booting, or check to see if they're running.", ephemeral=True)
        return

    # Create SelectOption instances from subscription_plans
    options = [discord.SelectOption(label=name, value=name) for name in subscription_plans.keys()]
    
    # Ensure we have at least one option
    if not options:
        await interaction.response.send_message("If you're seeing this this means either InviteShopBot or InviteShopHelper are not fully online, wait for them to finish booting, or check to see if they're running.", ephemeral=True)
        return

    # Create Select component with options
    select = Select(placeholder="Choose a subscription plan", options=options)
    
    view = View()
    view.add_item(select)
    
    # Callback for selection
    async def select_callback(interaction: discord.Interaction):
        selected_plan = select.values[0]
        await interaction.response.send_message(f"You selected: `{amount}x` of `{selected_plan}`, costing `{shop_cost}` per item. You will recieve a followup message sometime soon, unfortunately the time it takes depends on whether or not discord is ratelimiting us.")

        # Helper processing
        helper = await bot.fetch_user(invite_shop_helper)
        sku_id = subscription_plans[selected_plan]
        await helper.send(f"/purchase|{interaction.user.id}|{selected_plan}|{shop_cost}|{sku_id}|{amount}|")

    select.callback = select_callback
    
    # Send initial response with selection view
    await interaction.response.send_message("Please select a subscription plan:", view=view)


bot.run(token)