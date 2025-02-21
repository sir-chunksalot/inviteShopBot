import discord
import discord.sku

token = "MTM0MjMzNzU4NDg2MDIzMzc4OA.G8p8L3.VR_CUD8OPccD6zWdaRaWxPhcCP4kTWp5lSJlJY"

client = discord.Client()



@client.event
async def on_ready():
    print(f'We have logged in as {client.user}')

@client.event
async def on_message(message): 
    if message.content.startswith('$shop'):
       await message.channel.send('shop accessed')

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
            


client.run(token)