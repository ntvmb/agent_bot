import logging
import asyncio
import json
import discord
from discord import (
    option,
    default_permissions,
    SlashCommandOptionType,
    guild_only,
    Option,
)
from discord.ext import tasks, commands
from . import server_vars
from . import global_vars
from .uptime import process_uptime_human_readable

bot = discord.Bot(intents=discord.Intents.all())
_log = logging.getLogger(__name__)


@bot.event
async def on_ready():
    watching = discord.Activity(
        type=discord.ActivityType.listening, name="to the honeypots"
    )
    await bot.change_presence(activity=watching, status=discord.Status.dnd)
    _log.info(f"Logged in as {bot.user}.")
    global_vars.write("guild_count", len(bot.guilds))


@bot.slash_command(name="ping", description="Pong!")
async def ping(ctx: discord.ApplicationContext):
    from time import perf_counter_ns

    t1 = perf_counter_ns()
    await ctx.defer()
    t2 = perf_counter_ns()
    # How long did it take to defer the interaction?
    await ctx.respond(f"Pong! `{(t2 - t1)/1e6:.0f} ms`")
