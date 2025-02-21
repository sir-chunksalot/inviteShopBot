import discord
import discord.sku
import os

token = "MTM0MjMzNzU4NDg2MDIzMzc4OA.G8p8L3.VR_CUD8OPccD6zWdaRaWxPhcCP4kTWp5lSJlJY"

client = discord.Client()
INVITE_FILE = 'main/invites.txt'


@client.event
async def on_ready():
    print(f'We have logged in as {client.user}')

@client.event
async def on_message(message): 
    if message.content.startswith('$shop'):
        try:
            with open('main/nitro_codes.txt', 'r') as file:
                lines = file.readlines()
                
            shop_message = "Welcome to the Nitro Shop! Here's what we have:\n\n"
            count = 0
            for line in lines:
                count += 1
                if count == 1: 
                    continue
                parts = line.split(" | ")
                subscription_type = parts[0] 
                cost = parts[1]
                shop_message += f"{subscription_type}: `{cost}`\n"
            await message.channel.send(shop_message)
            
        except Exception as e:
            await message.channel.send(f"An error occurred while reading the file: {e}")

    if message.content.startswith('$invite'):
        channel = message.channel

        mentioned_user = message.author
        if message.mentions:
            mentioned_user = message.mentions[0]
        invites = await channel.invites()
        
        count = 0
        for invite in invites:
            if invite.inviter == mentioned_user:
                count += invite.uses
                
        await message.channel.send(f'This user has sent {count} invite(s)')
    
    if message.content.startswith('$leaderboard'):
        try:
            with open(INVITE_FILE, 'r') as file:
                lines = file.readlines()
            leaderboard_message = 'Lifetime Invite Leaderboard\n\n'
            
            for line in lines:
                parts = line.split(" | ")
                username = parts[0]
                lifetime_invites = [1]
                current_cash = [2]
                leaderboard_message += f"`{username}`: Lifetime Invites\n"
        except Exception as e:
             await message.channel.send(f"An error occurred while reading the file: {e}")
            
    if message.content.startswith('$debug'): #REMOVE BEFORE PUBLISHING
        print(os.listdir())
        
@client.event
async def on_member_join(ctx):
    #use new_member to verfiy its a legit invite
    #url to find which link it was 
    invites = await ctx.channel.invites()

            


client.run(token)