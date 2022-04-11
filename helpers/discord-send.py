#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import discord, sys, time

# The supplied init file path (argv[0]) will define url_webhook, message_id, and message
url_webhook    = None
message_header = None
message        = None
delete_after   = None
exec(open(sys.argv[1], 'r', encoding="utf8").read())

# Create the webhook
webhook = discord.Webhook.from_url(url_webhook, adapter=discord.RequestsWebhookAdapter())

# Sending by embed makes it prettier and larger
e = discord.Embed()
e.color       = 15548997 # Red
e.description = message.strip()

# Send it!
if message_header == None: message_header = ''
message = webhook.send(message_header, embeds=[e], wait=True)

# If we're supposed to delete...
if delete_after:
  time.sleep(60*delete_after)
  webhook.delete_message(message.id)

