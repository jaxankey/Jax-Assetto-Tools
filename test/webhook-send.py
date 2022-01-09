#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import discord

webhook_url = "https://discord.com/api/webhooks/916450053240008824/rxZDFuZUQEhssJjU9YtP1XsmBztsK4K735b1N9lMpaljLTucfHQki6Hpfb56dMF4JgNj"

message = "On the <#!898719762098565140> right now!\nHop on <#777719281718132781>!"

embed = discord.Embed()

embed.title = "On "
embed.description = \
"""
test messsage <#898719762098565140>
"""
embed.set_footer(text = "FOOTER <#${898719762098565140}>")
embed.color = 15548997




# Open the webhook and send the message, then kill it later
webhook = discord.Webhook.from_url(webhook_url, adapter=discord.RequestsWebhookAdapter())
x = webhook.send(message, embeds=[embed], wait=True)
