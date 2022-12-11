import discord

import discord
intents = discord.Intents.default()
intents.typing = False
intents.presences = False

client = discord.Client(intents=intents)

@client.event
async def on_message(message):
    print('on_message', message)
    print(message.content)
    # if message.author == client.user:
    #     return
    # if message.content == "Hello":
    #     await client.send_message(channel, "Buzz buzz!")