#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import discord, sys

# The supplied init file path (argv[0]) will define url_webhook, message_id, and message
url_webhook = None
message     = None
message_id  = None
exec(open(sys.argv[0], 'r', encoding="utf8").read())

# Create the webhook
webhook = discord.Webhook.from_url(url_webhook, adapter=discord.RequestsWebhookAdapter())

# Sending by embed makes it prettier and larger
e = discord.Embed()
e.color       = 15548997 # Red
e.description = message

# Decide whether to make a new message or use the existing
if message_id:
    # Try to edit; if this fails, send.
    try:    webhook.edit_message(message_id, embeds=[e])
    except: webhook.send('', embeds=[e], wait=True).id
else:       webhook.send('', embeds=[e], wait=True).id
