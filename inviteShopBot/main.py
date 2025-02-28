import discord
from datetime import datetime, timezone
from discord.ext import commands
from discord.ui import Button, View
import aiosqlite
from collections import defaultdict

from discord import Embed

token = "MTM0MzM4MjQ5ODkxODQwNDIyNg.GeyYtG.lJ_lPBPNvxfZuZIV5ffaKsUdjoXEzMGsZ9WT1Y"

admin = [1229197671839826037, 456225181107486721]

embed = None
msg = None
multiplier = 10
intents = discord.Intents.all()
bot = commands.Bot(command_prefix='/', intents=intents)

INVITE_FILE = 'main/invites.txt'


@bot.event
async def on_ready():
    await bot.tree.sync()
    print(f'We have logged in as {bot.user}')
    async with aiosqlite.connect("user_invites.db") as db:
        async with db.cursor() as cursor:
            await cursor.execute("DROP TABLE IF EXISTS users") #delete later
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
                    
@bot.tree.command(name="fart") #delete later
async def fart(interaction:discord.Interaction):
    await interaction.response.send_message("i farted!1")


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
    
    for invite in invites:
        inviteTracking[invite.inviter.id] = inviteTracking.get(invite.inviter.id, 0) + invite.uses
    print(inviteTracking)
    async with aiosqlite.connect("user_invites.db") as db:
        async with db.cursor() as cursor:
            await cursor.execute("SELECT id, invites FROM users WHERE guild = ?", (guild_id,))
            db_users = await cursor.fetchall()
            
            #list of tuples
            for user_id, db_invites in db_users:
                if user_id in inviteTracking:
                    new_invites = inviteTracking[user_id]
                    print(f"{db_invites} fart {new_invites}")
                    if db_invites < new_invites:
                        print(f"User {user_id} has fewer invites in the database ({db_invites}) than in the new data ({new_invites})")
                        user = user_id #this is the user of who invited the new member. it is now not set to none, and currency will be awarded
                        await cursor.execute("""
                        UPDATE users
                        SET invites = ?
                        WHERE id = ? AND guild = ?
                    """, (new_invites, user_id, guild_id))
                        
            await cursor.execute("SELECT id FROM users WHERE id = ? AND guild = ?", (member.id, guild_id)) #counts as new user if the user isnt in this 
            db_member = await cursor.fetchone()
            
            if db_member is None:  # If the member doesn't exist in the database, add them
                new_member = True
                print(f"Adding new user {member.id} to the database")
                await cursor.execute("""
                    INSERT INTO users (id, name, invites, guild, coins)
                    VALUES (?, ?, 0, ?, 0)
                """, (member.id, member.name, guild_id))
                    
            await db.commit()

    
    if user != None and new_member:
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
        print('no valid user found')
    
    
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

        
@bot.command()
async def setshop(ctx):
    print('Shop has been set.')
    
            
    async with aiosqlite.connect('shop.db') as db:
        async with db.execute("SELECT name FROM sqlite_master WHERE type='table';") as cursor:
            tables = await cursor.fetchall()
    
    
    global embed
    global msg
    embed = Embed(
        color=discord.Color.dark_blue(),
        title='💰 Welcome to the `Invite Shop`! 💰',
        description="Click on buttons 1-5 to choose a category! Check your balance with the 🪙 button.\nConfused? Click on the 📝!"
        )
    
    table_count = 0
    for table in tables:
        category = table[0]
        if category == "sqlite_sequence":  #idk why i need this but stack overflow told me to :pray:
            continue
        table_count += 1
        async with aiosqlite.connect('shop.db') as db:
            async with db.execute(f"SELECT * FROM {category}") as cursor:
                items = await cursor.fetchall()
        embed.add_field(name="", value="", inline=False)
        embed.add_field(name=f"\n`{table_count}.` {category}!", value="", inline=False)
        
        

        count = 0
        item_grouped = {}

        # Group items by name and count occurrences
        for item in items:
            item_id, item_name, item_reward, item_cost, item_hidden = item
            
            if item_hidden == 1:
                continue
            
            if item_name not in item_grouped:
                item_grouped[item_name] = {
                    'cost': item_cost,
                    'stock': 0
                }
            
            item_grouped[item_name]['stock'] += 1

        # Add fields to the embed for each unique item
        for item_name, details in item_grouped.items():
            count += 1
            embed.add_field(
                name=f"Item {count}: {item_name}",
                value=f"\nCost: `{details['cost']}` 🪙\nStock: {details['stock']} ",
                inline=True
            )
        embed.add_field(name="", value=f"*Click the* `{table_count}` *button*\n*to buy something from*\n*this category.*", inline=True)

    
    button1 = CategorySelect(style=discord.ButtonStyle.blurple, emoji='1️⃣', tables=tables, value=1)
    button2 = CategorySelect(style=discord.ButtonStyle.blurple, emoji='2️⃣', tables=tables,value=2)
    button3 = CategorySelect(style=discord.ButtonStyle.blurple, emoji='3️⃣', tables=tables,value=3)
    button4 = CategorySelect(style=discord.ButtonStyle.blurple, emoji='4️⃣', tables=tables, value=4)
    button5 = CategorySelect(style=discord.ButtonStyle.blurple, emoji='5️⃣', tables=tables,value=5)
    guide_button = GuideButton()
    balance_button = BalanceButton()
    
    view = View()

    view.add_item(button1)
    view.add_item(button2)
    view.add_item(button3)
    view.add_item(button4)
    view.add_item(button5)
    view.add_item(guide_button)
    view.add_item(balance_button)
    
    
    
    

    msg = await ctx.channel.send(embed=embed, view=view)
    
    await update_shop(ctx)

async def update_shop(ctx):
    global embed
    #embed.add_field(name="Sorry! Shop is currently empty, please come back later.", value="0", inline=True)
    
    await msg.edit(embed=embed)
    

class CategorySelect(Button):
    def __init__(self, style, emoji, tables, value):
        super().__init__(style=style, emoji=emoji)
        self.tables = tables
        self.value = value - 1  # Adjust for 0-based index
    
    async def callback(self, interaction):
        embed = Embed(
            color=discord.Color.dark_blue(),
            title='`Available for Purchase`:',
            description=""
        )

        # Fetch the correct category based on the button clicked
        category = self.tables[self.value]
        category = category[0]
        print(category)
        async with aiosqlite.connect('shop.db') as db:
            try:
                # Using parameterized queries to avoid SQL injection
                async with db.execute(f"SELECT * FROM {category}") as cursor:
                    items = await cursor.fetchall()

                count = 0
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

                
                
                item_cost_dict = {}
                item_name_dict = {}
                item_id_dict = {}  
                for item_name, details in item_grouped.items():
                    count += 1
                    item_cost_dict[count] = details['cost']  
                    item_name_dict[count] = item_name
                    item_id_dict[count] = details['item_id'] 
                    embed.add_field(
                        name=f" | Item `{count}`: {item_name} | ",
                        value=f"Cost: `{details['cost']}` 🪙\nStock: {details['stock']} ",
                        inline=True
                    )
                
                embed.add_field(name="", value=f"Click the item number to purchase.", inline=True)

                # add purchase buttons for each item
                button1 = PurchaseButton(style=discord.ButtonStyle.blurple, emoji='1️⃣', item_cost=item_cost_dict.get(1), item_name=item_name_dict.get(1), item_id=item_id_dict.get(1), category=category)
                button2 = PurchaseButton(style=discord.ButtonStyle.blurple, emoji='2️⃣', item_cost=item_cost_dict.get(2), item_name=item_name_dict.get(2), item_id=item_id_dict.get(2), category=category)
                button3 = PurchaseButton(style=discord.ButtonStyle.blurple, emoji='3️⃣', item_cost=item_cost_dict.get(3), item_name=item_name_dict.get(3), item_id=item_id_dict.get(3), category=category)
                button4 = PurchaseButton(style=discord.ButtonStyle.blurple, emoji='4️⃣', item_cost=item_cost_dict.get(4), item_name=item_name_dict.get(4), item_id=item_id_dict.get(4), category=category)
                button5 = PurchaseButton(style=discord.ButtonStyle.blurple, emoji='5️⃣', item_cost=item_cost_dict.get(5), item_name=item_name_dict.get(5), item_id=item_id_dict.get(5), category=category)
                
                view = View()
                view.add_item(button1)
                view.add_item(button2)
                view.add_item(button3)
                view.add_item(button4)
                view.add_item(button5)
                
                await interaction.response.send_message(f"Here are the items available for purchase in the `{category}` category:", embed=embed, view=view, ephemeral=True)
            except Exception as e:
                print(f"Error fetching items from category {category}: {e}")
                await interaction.response.send_message(f"An error occurred while fetching items from the category `{category}`.", ephemeral=True)


class PurchaseButton(Button):
    global item_cost
    global item_name
    global item_id
    global category
    
    def __init__(self, style, emoji, item_cost, item_name, item_id, category):
        super().__init__(style=style,emoji=emoji)
        self.item_cost = item_cost
        self.item_name = item_name
        self.item_id = item_id
        self.category = category
        
    
    async def callback(self, interaction):
        print(f'value={self.item_id}')
        
        view =  View()
        confirm_button = ShopConfirmButton(self.category, self.item_id)
        deny_button = DenyButton()
        view.add_item(confirm_button)
        view.add_item(deny_button)
        await interaction.response.send_message(f"You are trying to purchase {self.item_name} for {self.item_cost}. Are you sure you want to do this?", view=view, ephemeral=True)

class ShopConfirmButton(Button):
    global line_id
    global category
    def __init__(self, category, line_id):
        super().__init__(style=discord.ButtonStyle.green, emoji='✅')
        self.category = category
        self.line_id = line_id
        
    async def callback(self, interaction):
        await interaction.response.send_message("Purchase successful!", ephemeral=True)
        await delete_line(self.category, self.line_id)
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
        super().__init__(style=discord.ButtonStyle.gray, emoji='📝')
    async def callback(self, interaction):
        await interaction.response.send_message("**How does this bot work?**\nThis shop operates with `Invite Tokens`.\n\nYou gain these tokens by inviting new users to this server.\n\n**How do I invite people to the server?**\n-Click the dropdown next to the servers name in the top left.\n-Next, click `Invite People`.\n-Click any user on your friends list. \n-As soon as a new user accepts one of your invites, you will be automatically awarded with currency!\n\nIt's that simple, good luck!", ephemeral=True)
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
async def delete_line(category: str, line_id: int):
    async with aiosqlite.connect("shop.db") as db:
        async with db.cursor() as cursor:
            await cursor.execute(f"DELETE FROM {category} WHERE id = ?", (line_id,))
            await db.commit()

    
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
            #call edit shop function
            
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
    #call edit shop function
    
@bot.tree.command(name="delete", description="Delete the specified table or just a line from that table.")
async def delete(interaction:discord.Interaction, category: str, line_id: int = None):
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


async def insert_shop_item(ctx):
    global embed
    embed.add_field(name="Test item", value="Description of test item", inline=False)
    
    await msg.edit(embed=embed)
    


bot.run(token)