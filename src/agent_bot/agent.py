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


@bot.event
async def on_application_command_error(
    ctx: discord.ApplicationContext, error: Exception
):
    if isinstance(error, commands.errors.MissingPermissions) or isinstance(
        error, commands.errors.NotOwner
    ):
        try:
            await ctx.respond(
                "I'm sorry, but I cannot let you do that.",
                ephemeral=True,
            )
        except Exception:
            _log.exception("Failed to send response.")
        _log.warning(
            f"{ctx.author} attempted to execute {ctx.command.name}, but does not have permission."
        )
    elif isinstance(error, commands.errors.NoPrivateMessage):
        try:
            await ctx.respond(
                "This command cannot be used in a DM context.", ephemeral=True
            )
        except Exception:
            _log.exception("Failed to send response.")
    else:
        _log.exception(
            f"An exception occurred while executing {ctx.command.name}.",
            exc_info=(type(error), error, error.__traceback__),
        )
        try:
            await ctx.respond(
                f"An exception occurred while executing this command:\n{error}",
                ephemeral=True,
            )
        except Exception:
            _log.exception("Failed to send response.")


@bot.event
async def on_message(message: discord.Message):
    # Only act on messages in servers
    if not isinstance(message.author, discord.Member):
        return
    # Don't respond to the bot's own messages
    if message.author.id == bot.user.id:
        return
    honeypot = server_vars.get("honeypot", message.guild.id)
    if (
        honeypot is not None
        and message.channel.id == honeypot
        and not message.author.bot
    ):
        try:
            await message.author.ban(
                delete_message_seconds=86400, reason="Fell for the honeypot"
            )
            _log.info(f"The honeypot in {message.guild} caught {message.author}!")
        except discord.errors.HTTPException:
            _log.exception(f"Failed to ban {message.author} from {message.guild}!")
            return


def _has_correct_permissions(
    ctx: discord.ApplicationContext, channel: discord.TextChannel
) -> bool:
    perms = channel.permissions_for(ctx.me)
    return perms.send_messages and perms.ban_members


@bot.slash_command(name="ping", description="Pong!")
async def ping(ctx: discord.ApplicationContext):
    from time import perf_counter_ns

    t1 = perf_counter_ns()
    await ctx.defer()
    t2 = perf_counter_ns()
    # How long did it take to defer the interaction?
    await ctx.respond(f"Pong! `{(t2 - t1)/1e6:.0f} ms`")


@bot.slash_command(name="uptime", description="Check Agent's uptime.")
async def uptime(ctx: discord.ApplicationContext):
    await ctx.respond(process_uptime_human_readable())


@bot.slash_command(name="set_honeypot", description="Set the honeypot channel.")
@default_permissions(manage_channels=True)
@guild_only()
async def set_honeypot(
    ctx: discord.ApplicationContext,
    channel: Option(discord.TextChannel, description="The channel to use."),  # type: ignore
):
    await ctx.defer(ephemeral=True)
    if _has_correct_permissions(ctx, channel):
        server_vars.write("honeypot", channel.id, ctx.guild_id)
        await ctx.respond(f"Okay, I will now monitor {channel.mention}.")
    else:
        await ctx.respond(
            "I cannot do as told because I do not have the correct permissions.\n"
            "Make sure I have the `Send Messages` and `Ban Members` permissions."
        )
